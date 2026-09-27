"""Конфигурация проекта"""

from pathlib import Path
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    STORAGE_DIR: Path = "storage"
    DATABASE_URL: str = "sqlite:///./voxsync.db"

    # Настройки AI моделей
    WHISPER_MODEL: str = "small"
    TTS_VOICE: str = "ru-RU-DmitryNeural"

    class Config:
        env_file = ".env"

settings = Settings()