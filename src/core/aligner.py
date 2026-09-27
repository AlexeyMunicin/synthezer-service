import logging
import os
import tempfile
import subprocess
from pathlib import Path
from pydub import AudioSegment
from src.core.transcriber import Segment

logger = logging.getLogger(__name__)

class AudioAligner:
    """Модуль выравнивает аудиодорожки. Ускоряет сгенерированую речь
    чтобы она совпадала с оригиналом
    """
    def __init__(self, max_speedup: float = 1.35):
        self.max_speedup = max_speedup
    
    def __speedup_ffmpeg(self, audio: AudioSegment, speed: float) -> AudioSegment:
        """ускорение без изменения высоты голоса (Pitch) через FFmpeg"""
        if speed <= 1.0:
            return audio
        
        # используем временные файлы для передачи данных в FFmpeg

        with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_in, \
        tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as f_out:
            
            temp_in = f_in.name
            temp_out = f_out.name

        try:
            audio.export(temp_in, format="wav")

            safe_speed = min(speed, 1.4)

            cmd = [
               "ffmpeg", "-y", "-v", "error",
                "-i", temp_in,
                "-filter:a", f"atempo={safe_speed}",
                "-vn", temp_out 
            ]

            subprocess.run(cmd, check=True)

            if os.path.exists(temp_out):
                return AudioSegment.from_wav(temp_out)
            else:
                return audio
            
        except Exception as e:
            logger.error(f"Ошибка ускорения FFmpeg: {e}")
            return audio
        finally:
            # очистка мусора
            if os.path.exists(temp_in): os.remove(temp_in)
            if os.path.exists(temp_out): os.remove(temp_out)

    def align(self, segments: list[Segment], audio_files: list[Path]) -> AudioSegment:
        """
        Собирает все кусочки в одну длинную аудиодорожку.
        """
        if not segments or not audio_files:
            return AudioSegment.silent(duration=1000)

        # Длина итоговой дорожки
        total_duration_ms = int(segments[-1].end * 1000) + 2000
        final_track = AudioSegment.silent(duration=total_duration_ms)
        
        logger.info("Сборка аудиодорожки (Элайнер)...")

        for i, (seg, path) in enumerate(zip(segments, audio_files)):
            if not path.exists():
                continue
            
            clip = AudioSegment.from_file(path)
            start_ms = int(seg.start * 1000)
            
            # Окно: от начала текущей фразы до начала следующей
            if i < len(segments) - 1:
                next_start_ms = int(segments[i+1].start * 1000)
                available_ms = next_start_ms - start_ms
            else:
                available_ms = len(clip) + 1000 # Запас для последней фразы
            
            # Расчет коэффициента ускорения
            speed_factor = 1.0
            if len(clip) > available_ms:
                speed_factor = len(clip) / available_ms
                if speed_factor > self.max_speedup:
                    speed_factor = self.max_speedup
            
            # Применение ускорения (>5% разницы)
            if speed_factor > 1.05:
                clip = self.__speedup_ffmpeg(clip, speed_factor)
            
            # Наложение на общий таймлайн
            final_track = final_track.overlay(clip, position=start_ms)

        logger.info("Сборка аудиодорожки завершена.")
        return final_track

        
