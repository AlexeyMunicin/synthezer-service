import uuid
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import BackgroundTasks, Depends, FastAPI, Form, HTTPException, status
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy.orm import Session

from src.api.auth import (
    create_access_token,
    get_current_user,
    hash_password,
    verify_password,
)
from src.database.db import get_db, init_db
from src.database.job_service import (
    create_job,
    delete_expired_files,
    get_job,
    get_user_jobs,
    update_job,
)
from src.database.models import User
from src.pipeline import DubbingPipeline


# ---------- Lifespan (инициализация при старте) ----------

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="VOXsync API", lifespan=lifespan)

# ---------- Статика ----------

app.mount("/storage", StaticFiles(directory="storage"), name="storage")

FRONTEND_DIST = Path("frontend/dist")

# Фронтенд-ассеты (JS/CSS) отдаём через mount на /assets
# НЕ монтируем "/" чтобы не перехватывать POST /api/* запросы
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=str(FRONTEND_DIST / "assets")), name="assets")
    # favicon и иконки из public/
    _public = Path("frontend/public")
    if _public.exists():
        app.mount("/icons", StaticFiles(directory=str(_public)), name="public")


# ---------- Пайплайн (ленивая инициализация) ----------

pipeline: DubbingPipeline | None = None


def get_pipeline() -> DubbingPipeline:
    global pipeline
    if pipeline is None:
        pipeline = DubbingPipeline()
    return pipeline


# ---------- Вспомогательные функции ----------

def _job_urls(job_id: str, target_lang: str) -> dict:
    base = f"/storage/jobs/{job_id}"
    return {
        "video_url": f"{base}/final_{target_lang}.mp4",
        "subtitles_url": f"{base}/subtitles.vtt",
    }


def _job_to_dict(job) -> dict:
    return {
        "job_id": job.id,
        "status": job.status,
        "stage": job.stage,
        "progress": job.progress,
        "url": job.url,
        "target_lang": job.target_lang,
        "video_url": job.video_url,
        "subtitles_url": job.subtitles_url,
        "error": job.error,
        "created_at": job.created_at.isoformat() if job.created_at else None,
        "expires_at": job.expires_at.isoformat() if job.expires_at else None,
        "files_deleted": job.files_deleted,
    }


# ---------- Фоновая задача ----------

async def background_process(job_id: str, url: str, target_lang: str) -> None:
    """Выполняется в фоне FastAPI. Обновляет статус задачи в БД."""
    from src.database.db import SessionLocal
    db = SessionLocal()
    try:
        update_job(db, job_id, status="processing", stage="download", progress=5)

        success = await get_pipeline().process_video(url, job_id, target_lang)

        if success:
            urls = _job_urls(job_id, target_lang)
            update_job(
                db, job_id,
                status="done",
                stage="done",
                progress=100,
                video_url=urls["video_url"],
                subtitles_url=urls["subtitles_url"],
            )
        else:
            update_job(db, job_id, status="error", stage="error", progress=100,
                       error="Пайплайн завершился с ошибкой")
    except Exception as e:
        update_job(db, job_id, status="error", stage="error", progress=100, error=str(e))
    finally:
        db.close()


# ================================================================
# AUTH ENDPOINTS
# ================================================================

@app.post("/api/register", status_code=201)
async def register(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Регистрация нового пользователя."""
    if db.query(User).filter(User.email == email).first():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email уже используется",
        )
    if len(password) < 6:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Пароль должен содержать минимум 6 символов",
        )
    user = User(email=email, hashed_password=hash_password(password))
    db.add(user)
    db.commit()
    db.refresh(user)

    token = create_access_token(user.id)
    return JSONResponse({"access_token": token, "token_type": "bearer", "email": user.email})


@app.post("/api/login")
async def login(
    email: str = Form(...),
    password: str = Form(...),
    db: Session = Depends(get_db),
):
    """Вход — возвращает JWT-токен."""
    user = db.query(User).filter(User.email == email).first()
    if not user or not verify_password(password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Неверный email или пароль",
        )
    token = create_access_token(user.id)
    return JSONResponse({"access_token": token, "token_type": "bearer", "email": user.email})


@app.get("/api/me")
async def me(current_user: User = Depends(get_current_user)):
    """Возвращает данные текущего пользователя."""
    return JSONResponse({"id": current_user.id, "email": current_user.email})


# ================================================================
# PIPELINE ENDPOINTS
# ================================================================

@app.post("/api/process")
async def start_processing(
    background_tasks: BackgroundTasks,
    url: str = Form(...),
    target_lang: str = Form("ru"),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Запускает задачу дубляжа. Требует авторизации."""
    job_id = str(uuid.uuid4())
    create_job(db, job_id=job_id, user_id=current_user.id, url=url, target_lang=target_lang)
    background_tasks.add_task(background_process, job_id, url, target_lang)
    return JSONResponse({"job_id": job_id})


@app.get("/api/status/{job_id}")
async def job_status(
    job_id: str,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Статус конкретной задачи."""
    job = get_job(db, job_id)
    if not job or job.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Задача не найдена")
    return JSONResponse(_job_to_dict(job))


@app.get("/api/jobs")
async def list_jobs(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """История задач текущего пользователя (последние 50)."""
    jobs = get_user_jobs(db, current_user.id)
    return JSONResponse([_job_to_dict(j) for j in jobs])


# ================================================================
# ADMIN / MAINTENANCE
# ================================================================

@app.post("/api/admin/cleanup")
async def cleanup_expired(db: Session = Depends(get_db)):
    """Удаляет файлы задач с истёкшим TTL. В продакшене — вызывать через cron."""
    count = delete_expired_files(db)
    return JSONResponse({"deleted_jobs": count})


# ================================================================
# SPA CATCH-ALL — должен быть последним!
# ================================================================

@app.get("/favicon.svg", include_in_schema=False)
async def favicon():
    f = Path("frontend/public/favicon.svg")
    if f.exists():
        return FileResponse(str(f), media_type="image/svg+xml")
    return JSONResponse({"detail": "not found"}, status_code=404)


@app.get("/{full_path:path}", include_in_schema=False)
async def spa_fallback(full_path: str):
    """Отдаёт index.html для всех GET-запросов, не совпавших с API-роутами.
    Это нужно для React Router (client-side routing).
    """
    index = FRONTEND_DIST / "index.html"
    if index.exists():
        return FileResponse(str(index))
    return JSONResponse({"detail": "Frontend not built"}, status_code=404)
