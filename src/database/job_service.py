import shutil
import logging
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from sqlalchemy.orm import Session

from src.database.models import Job

logger = logging.getLogger(__name__)

JOB_TTL_DAYS = 3  # Файлы хранятся 3 дня


def create_job(db: Session, job_id: str, user_id: int, url: str, target_lang: str) -> Job:
    """Создаёт запись о задаче в БД."""
    expires_at = datetime.now(timezone.utc) + timedelta(days=JOB_TTL_DAYS)
    job = Job(
        id=job_id,
        user_id=user_id,
        url=url,
        target_lang=target_lang,
        status="queued",
        stage="queued",
        progress=0,
        expires_at=expires_at,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def update_job(db: Session, job_id: str, **kwargs) -> Optional[Job]:
    """Обновляет поля задачи."""
    job = db.query(Job).filter(Job.id == job_id).first()
    if not job:
        return None
    for key, value in kwargs.items():
        setattr(job, key, value)
    db.commit()
    db.refresh(job)
    return job


def get_job(db: Session, job_id: str) -> Optional[Job]:
    return db.query(Job).filter(Job.id == job_id).first()


def get_user_jobs(db: Session, user_id: int, limit: int = 50) -> list[Job]:
    """Возвращает историю задач пользователя (новые сначала)."""
    return (
        db.query(Job)
        .filter(Job.user_id == user_id)
        .order_by(Job.created_at.desc())
        .limit(limit)
        .all()
    )


def delete_expired_files(db: Session, storage_path: Path = Path("storage")) -> int:
    """
    Удаляет файлы задач, у которых истёк TTL.
    Возвращает количество очищенных задач.
    """
    now = datetime.now(timezone.utc)
    expired_jobs = (
        db.query(Job)
        .filter(Job.expires_at <= now, Job.files_deleted == False)  # noqa: E712
        .all()
    )

    count = 0
    for job in expired_jobs:
        job_dir = storage_path / "jobs" / job.id
        if job_dir.exists():
            try:
                shutil.rmtree(job_dir)
                logger.info(f"Удалены файлы задачи {job.id} (TTL истёк)")
            except Exception as e:
                logger.error(f"Не удалось удалить {job_dir}: {e}")
                continue

        job.files_deleted = True
        job.video_url = None
        job.subtitles_url = None
        count += 1

    db.commit()
    return count
