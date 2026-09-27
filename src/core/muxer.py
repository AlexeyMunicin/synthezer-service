import logging
import subprocess
from pathlib import Path

logger = logging.getLogger(__name__)

class VideoMuxer:
    """Модуль для микширования (склейки) оригинального видео, новой озвучки и субтитров."""
    
    def __init__(
        self,
        original_volume: float = 0.1,
        dubbed_volume: float = 1.5,
        mix_original: bool = False,
    ):
        self.original_volume = original_volume
        self.dubbed_volume = dubbed_volume
        self.mix_original = mix_original

    def mix(self, video_path: Path, dubbed_audio_path: Path, output_path: Path, subtitles_path: Path | None = None) -> Path:
        if not video_path.exists():
            raise FileNotFoundError(f"Исходное видео не найдено: {video_path}")
        if not dubbed_audio_path.exists():
            raise FileNotFoundError(f"Аудиодорожка перевода не найдена: {dubbed_audio_path}")

        mode = "MIX" if self.mix_original else "REPLACE"
        logger.info(f"Сборка финального видео (audio={mode}, subs={bool(subtitles_path)}): {output_path.name}...")

        # Базовая команда
        cmd = ["ffmpeg", "-y"]
        
        # Входы (Inputs)
        cmd.extend(["-i", str(video_path)])         # Вход 0: Видео
        cmd.extend(["-i", str(dubbed_audio_path)])  # Вход 1: Аудио
        
        if subtitles_path and subtitles_path.exists():
            cmd.extend(["-i", str(subtitles_path)]) # Вход 2: Субтитры

        # Маппинг (что берем из входов)
        if self.mix_original:
            cmd.extend([
                "-filter_complex",
                f"[0:a]volume={self.original_volume}[orig];"
                f"[1:a]volume={self.dubbed_volume}[dub];"
                f"[orig][dub]amix=inputs=2:duration=first:dropout_transition=2[audio_out]",
                "-map", "0:v",         # Видео из 0
                "-map", "[audio_out]"  # Сведенное аудио
            ])
        else:
            cmd.extend([
                "-map", "0:v:0",       # Видео из 0
                "-map", "1:a:0"        # Аудио из 1
            ])

        # Если есть субтитры, добавляем их маппинг
        if subtitles_path and subtitles_path.exists():
            cmd.extend([
                "-map", "2:s:0",       # Субтитры из 2
                "-c:s", "mov_text"     # Кодек субтитров для формата MP4
            ])

        # Общие настройки кодеков
        cmd.extend([
            "-c:v", "copy",            # Копируем видео без пережатия
            "-c:a", "aac",             # Жмем звук в AAC
            "-b:a", "192k",            # Битрейт звука
        ])

        if not self.mix_original:
            cmd.append("-shortest")    # Обрезаем по самому короткому потоку (если не миксуем)

        cmd.append(str(output_path))

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                logger.error(f"Ошибка FFmpeg:\n{result.stderr}")
                raise RuntimeError("FFmpeg не смог собрать видео.")
                
            logger.info("✅ Финальное видео успешно собрано!")
            return output_path
            
        except Exception as e:
            logger.error(f"Сбой в VideoMuxer: {e}")
            raise