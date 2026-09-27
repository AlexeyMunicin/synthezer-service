import logging
from pathlib import Path

# Предполагается, что настройки лежат в src.config
from src.config import settings

# Импорты твоих модулей
from src.core.downloader import VideoDownloader
from src.core.transcriber import Transcriber
from src.core.translator import Translator
from src.core.synthesizer import TTSProcessor
from src.core.muxer import VideoMuxer
from src.core.languages import get_language_config

logger = logging.getLogger(__name__)

class DubbingPipeline:
    def __init__(self):
        logger.info("Инициализация компонентов пайплайна...")
        self.downloader = VideoDownloader()
        self.transcriber = Transcriber()
        # Инициализируем 1 раз, чтобы LLM (4 ГБ) загрузилась в ОЗУ только один раз при старте сервера
        self.translator = Translator("ru") 
        self.tts = TTSProcessor("ru")
        self.muxer = VideoMuxer(mix_original=True)
        logger.info("Пайплайн готов к работе.")

    async def process_video(self, url: str, job_id: str, target_lang: str) -> bool:
        """Основной процесс обработки одного видео"""
        logger.info(f"🚀 Старт задачи {job_id} | Язык: {target_lang}")
        
        # Директория для конкретной задачи
        job_dir = Path("storage/jobs") / job_id
        job_dir.mkdir(parents=True, exist_ok=True)

        try:
            # ---> МАГИЯ: Меняем язык "на лету" без перезагрузки модели <---
            new_lang_config = get_language_config(target_lang)
            self.translator.lang_config = new_lang_config
            self.tts.lang_config = new_lang_config

            # 1. Скачивание
            dl_result = self.downloader.download(url, job_id)
            
            # 2. Транскрибация
            transcription = self.transcriber.transcribe(dl_result.audio_path)
            
            # 3. Перевод
            translated_segments = self.translator.translate_segments(transcription.segments)
            
            # 4. Сохраняем субтитры для веб-плеера (на переведенном языке)
            vtt_path = job_dir / "subtitles.vtt"
            self._save_vtt(translated_segments, vtt_path)
            
            # 5. Синтез (TTS)
            dubbed_audio_path = await self.tts.synthesize(translated_segments, job_dir)
            
            # 6. Склейка видео и звука
            final_video_path = job_dir / f"final_{target_lang}.mp4"
            self.muxer.mix(
                video_path=dl_result.video_path, 
                dubbed_audio_path=dubbed_audio_path, 
                output_path=final_video_path,
                subtitles_path=vtt_path 
            )
            
            logger.info(f"✅ Задача {job_id} успешно завершена!")
            return True

        except Exception as e:
            logger.error(f"❌ Ошибка в задаче {job_id}: {e}", exc_info=True)
            return False

    def _save_vtt(self, segments, filepath: Path):
        """Конвертирует сегменты в формат WebVTT (понимают все HTML5 плееры)"""
        with open(filepath, "w", encoding="utf-8") as f:
            f.write("WEBVTT\n\n")
            for i, seg in enumerate(segments, 1):
                start = self._format_time(seg.start)
                end = self._format_time(seg.end)
                f.write(f"{i}\n{start} --> {end}\n{seg.text}\n\n")

    def _format_time(self, seconds: float) -> str:
        """Форматирует секунды в формат 00:00:00.000"""
        h = int(seconds // 3600)
        m = int((seconds % 3600) // 60)
        s = int(seconds % 60)
        ms = int((seconds % 1) * 1000)
        return f"{h:02d}:{m:02d}:{s:02d}.{ms:03d}"