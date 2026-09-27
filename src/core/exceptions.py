from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class BaseError(Exception):
    """Базовая ошибка сервиса"""
    
    message: str
    timestamp: datetime = field(default_factory=datetime.now)
    original_error: Exception | None = None
    
    def __str__(self) -> str:
        parts = [self.message]
        if self.original_error:
            parts.append(f"Причина: {type(self.original_error).__name__}: {self.original_error}")
        return " | ".join(parts)
    
    def to_dict(self) -> dict:
        return {
            "error": self.__class__.__name__.lower(),
            "message": self.message,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class DownloadError(BaseError):
    """Ошибка при скачивании видео"""
    url: str | None = None
    
    def __str__(self) -> str:
        base = super().__str__()
        if self.url:
            return f"{base} | URL: {self.url}"
        return base


@dataclass
class TranscriptionError(BaseError):
    """Ошибка при транскрибации аудио"""
    audio_path: str | None = None
    
    def __str__(self) -> str:
        base = super().__str__()
        if self.audio_path:
            return f"{base} | File: {self.audio_path}"
        return base