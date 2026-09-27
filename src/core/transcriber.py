import logging
from pathlib import Path
from dataclasses import dataclass

import mlx_whisper
import librosa

from src.config import settings
from src.core.exceptions import TranscriptionError
from src.core.analyzer import AudioAnalyzer

logger = logging.getLogger(__name__)


@dataclass
class Segment:
    """Сегмент транскрипции с таймингами"""
    start: float
    end: float
    text: str
    speaker_id: str = "SPEAKER_00" 
    gender: str = "male" 
    
    @property
    def duration(self) -> float:
        return self.end - self.start


@dataclass
class TranscriptionResult:
    """Результат транскрибации"""
    text: str
    segments: list[Segment]
    language: str
    duration: float
    
    def to_srt(self) -> str:
        """Конвертация в SRT формат"""
        lines = []
        for i, seg in enumerate(self.segments, 1):
            start = self._format_timestamp(seg.start)
            end = self._format_timestamp(seg.end)
            lines.append(f"{i}")
            lines.append(f"{start} --> {end}")
            lines.append(seg.text.strip())
            lines.append("")
        return "\n".join(lines)
    
    @staticmethod
    def _format_timestamp(seconds: float) -> str:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        millis = int((seconds % 1) * 1000)
        return f"{hours:02d}:{minutes:02d}:{secs:02d},{millis:03d}"


class Transcriber:
    """Транскрибация аудио с помощью Whisper"""
    
    # Доступные модели и их размеры
    MODELS = {
        "tiny": "mlx-community/whisper-tiny-mlx",
        "base": "mlx-community/whisper-base-mlx",
        "small": "mlx-community/whisper-small-mlx",
        "medium": "mlx-community/whisper-medium-mlx",
        "large-v3": "mlx-community/whisper-large-v3-mlx",
    }
    
    def __init__(self, model_name: str | None = None):
        self.model_name = model_name or settings.whisper_model
        self.model_path = self.MODELS.get(self.model_name)
        
        if not self.model_path:
            raise ValueError(f"Неизвестная модель: {self.model_name}. Доступны: {list(self.MODELS.keys())}")
        
        self.analyzer = AudioAnalyzer()
        
        logger.info(f"Инициализация Whisper: {self.model_name}")
    
    def transcribe(self, audio_path: Path, language: str | None = None) -> TranscriptionResult:
        """
        Транскрибирует аудиофайл
        
        Args:
            audio_path: Путь к аудиофайлу
            language: Язык аудио (None для автоопределения)
            
        Returns:
            TranscriptionResult с текстом и таймингами
        """
        if not audio_path.exists():
            raise TranscriptionError(
                message="Аудиофайл не найден",
                audio_path=str(audio_path),
            )
        
        logger.info(f"Транскрибация: {audio_path}")
        
        try:
            result = mlx_whisper.transcribe(
                str(audio_path),
                path_or_hf_repo=self.model_path,
                language=language,
                word_timestamps=True,
            )

            logger.info("Загрузка аудио в RAM для DSP-анализа пола спикеров...")
            try:
                # sr=16000 (16 кГц) - это стандарт для анализа человеческого голоса
                y, sr = librosa.load(str(audio_path), sr=16000)
                dsp_available = True
            except Exception as e:
                logger.error(f"Не удалось загрузить аудио для librosa: {e}")
                dsp_available = False
            
            segments = []
            
            for seg in result["segments"]:
                start = seg["start"]
                end = seg["end"]
                text = seg["text"]

                gender = "male"
                if dsp_available:
                    gender = self.analyzer.detect_gender(y, sr, start, end)
                
                segments.append(
                    Segment(
                        start=start,
                        end=end,
                        text=text,
                        gender=gender
                    )
                )

            total_duration = segments[-1].end if segments else 0.0
            
            transcription = TranscriptionResult(
                text=result["text"],
                segments=segments,
                language=result.get("language", "unknown"),
                duration=total_duration,
            )
            
            males = sum(1 for s in segments if s.gender == "male")
            females = len(segments) - males
            logger.info(f"Транскрибация завершена: {len(segments)} сегментов (М: {males}, Ж: {females}), язык: {transcription.language}")
            
            return transcription
            
        except Exception as e:
            logger.error(f"Ошибка транскрибации: {e}")
            raise TranscriptionError(
                message="Не удалось транскрибировать аудио",
                audio_path=str(audio_path),
                original_error=e,
            ) from e