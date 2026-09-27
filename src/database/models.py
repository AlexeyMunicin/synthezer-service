from datetime import datetime, timezone
from sqlalchemy import Column, String, Integer, Float, DateTime, ForeignKey, Boolean
from sqlalchemy.orm import DeclarativeBase, relationship


class Base(DeclarativeBase):
    pass


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    email = Column(String, unique=True, index=True, nullable=False)
    hashed_password = Column(String, nullable=False)
    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    jobs = relationship("Job", back_populates="user", cascade="all, delete-orphan")


class Job(Base):
    __tablename__ = "jobs"

    id = Column(String, primary_key=True, index=True)  # UUID
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)

    url = Column(String, nullable=False)
    target_lang = Column(String, nullable=False, default="ru")

    status = Column(String, default="queued")   # queued | processing | done | error
    stage = Column(String, default="queued")
    progress = Column(Integer, default=0)

    video_url = Column(String, nullable=True)
    subtitles_url = Column(String, nullable=True)
    error = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    # Файлы автоматически удаляются через 3 дня; это поле фиксирует дату
    expires_at = Column(DateTime(timezone=True), nullable=True)
    files_deleted = Column(Boolean, default=False)

    user = relationship("User", back_populates="jobs")
