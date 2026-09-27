from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session
from typing import Generator

from src.database.models import Base

# SQLite файл лежит в корне проекта (рядом с storage/)
DATABASE_URL = "sqlite:///./voxsync.db"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # нужно для SQLite + FastAPI
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def init_db() -> None:
    """Создаёт все таблицы при первом запуске."""
    Base.metadata.create_all(bind=engine)


def get_db() -> Generator[Session, None, None]:
    """Dependency для FastAPI — открывает и закрывает сессию на запрос."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
