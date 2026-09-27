import logging
import subprocess
import time
from pathlib import Path
from dataclasses import dataclass

import yt_dlp

from src.config import settings
from src.core.exceptions import DownloadError

logger = logging.getLogger(__name__)

@dataclass
class DownloadResult:
    video_path: Path
    audio_path: Path
    title: str
    duration: float

class VideoDownloader:
    """Модуль для надежного скачивания видео с YouTube и других платформ"""
    
    def __init__(self, output_dir: Path | None = None, browser: str = "chrome", max_retries: int = 3):
        self.output_dir = output_dir or settings.tmp_dir
        # Браузер, из которого тянем куки (chrome, safari, firefox, edge)
        self.browser = browser 
        self.max_retries = max_retries
        self.retry_delay = 3 # Пауза между попытками в секундах
        
    def _build_ydl_opts(self, out_template: str) -> dict:
        return {
            # Широкая цепочка fallback-форматов:
            # 1) лучшее mp4 видео ≤1080p + m4a аудио
            # 2) лучшее видео + лучшее аудио (ffmpeg смержит)
            # 3) любой mp4 с аудио
            # 4) просто лучший доступный
            "format": (
                "bestvideo[ext=mp4][height<=1080]+bestaudio[ext=m4a]"
                "/bestvideo[height<=1080]+bestaudio"
                "/best[ext=mp4]"
                "/best"
            ),

            "outtmpl": out_template,
            "merge_output_format": "mp4",

            "quiet": True,
            "no_warnings": True,

            "postprocessors": [{
                "key": "FFmpegVideoRemuxer",
                "preferedformat": "mp4",
            }],

            # Куки из браузера — нужны для YouTube авторизации
            "cookiesfrombrowser": (self.browser,),

            # Решение JS n-challenge через deno (требуется для YouTube)
            "remote_components": ["ejs:github"],

            "extractor_args": {
                "youtube": {
                    "player_client": ["ios", "android", "web"],
                }
            },
        }

    def download(self, url: str, job_id: str) -> DownloadResult:
        job_dir = self.output_dir / job_id
        job_dir.mkdir(parents=True, exist_ok=True)
        
        # Шаблон имени (yt-dlp сам подставит правильное расширение: mp4, webm и тд)
        out_template = str(job_dir / "original.%(ext)s")
        audio_path = job_dir / "original.wav"
        
        ydl_opts = self._build_ydl_opts(out_template)
        
        logger.info(f"Начинаю скачивание: {url} (Куки из: {self.browser})")
        
        last_error = None
        
        # Механизм повторных попыток (Retry Logic)
        for attempt in range(1, self.max_retries + 1):
            try:
                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    info = ydl.extract_info(url, download=True)
                
                # Получаем реальное расширение скачанного файла
                ext = info.get('ext', 'mp4')
                video_path = job_dir / f"original.{ext}"
                
                # Проверка: если файл почему-то не нашелся по имени
                if not video_path.exists():
                    found_files = list(job_dir.glob("original.*"))
                    video_files = [f for f in found_files if f.suffix != '.wav']
                    if not video_files:
                        raise FileNotFoundError("Файл видео не сохранен на диск")
                    video_path = video_files[0]

                # Извлекаем WAV для Whisper
                self._extract_audio(video_path, audio_path)
                
                result = DownloadResult(
                    video_path=video_path,
                    audio_path=audio_path,
                    title=info.get("title", "Unknown"),
                    duration=float(info.get("duration", 0.0)),
                )
                
                logger.info(f"✅ Видео успешно скачано: '{result.title}'")
                return result
                
            except yt_dlp.utils.DownloadError as e:
                last_error = e
                error_msg = str(e).lower()
                
                logger.warning(f"⚠️ Попытка {attempt}/{self.max_retries} не удалась. Ошибка: {e}")
                
                # Проверка на ошибку блокировки базы данных браузера (ОЧЕНЬ частая ошибка на Mac)
                if "database is locked" in error_msg or "sqlite3.operationalerror" in error_msg:
                    logger.error(f"❌ Браузер {self.browser.upper()} открыт и блокирует куки! ЗАКРОЙТЕ ЕГО ПОЛНОСТЬЮ (Cmd+Q) и перезапустите скрипт.")
                    break # Нет смысла делать retry, пока юзер не закроет браузер
                
                # Если ошибка авторизации/ботов — ждем и пробуем снова
                auth_errors = ['sign in', 'bot', '403', '401']
                if any(err in error_msg for err in auth_errors) and attempt < self.max_retries:
                    logger.info(f"Ожидание {self.retry_delay} сек. перед новой попыткой...")
                    time.sleep(self.retry_delay)
                    continue
                
                break # Выходим, если попытки кончились или ошибка фатальная
                
            except Exception as e:
                logger.error(f"Непредвиденная ошибка: {e}")
                raise DownloadError(message="Ошибка в процессе скачивания", url=url, original_error=e)
                
        # Если цикл завершился и мы здесь — скачивание провалилось
        raise DownloadError(
            message=f"Не удалось скачать видео после {self.max_retries} попыток.",
            url=url,
            original_error=last_error
        )

    def _extract_audio(self, video_path: Path, audio_path: Path) -> None:
        """Извлекает аудио в формате WAV (16kHz, Mono) для нейросетей"""
        if not video_path.exists():
             raise FileNotFoundError(f"Исходное видео не найдено: {video_path}")

        logger.info("🎵 Извлечение аудиодорожки (FFmpeg)...")
        
        cmd = [
            "ffmpeg", "-y", 
            "-i", str(video_path),
            "-vn",                      # Отключаем видеопоток
            "-acodec", "pcm_s16le",     # Аудиокодек WAV
            "-ar", "16000",             # Частота (идеально для Whisper)
            "-ac", "1",                 # Моно-звук
            str(audio_path)
        ]
        
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True)
        
        if result.returncode != 0:
            raise RuntimeError(f"FFmpeg ошибка извлечения звука: {result.stderr}")