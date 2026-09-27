import sys
import asyncio
import logging
from pathlib import Path

# Добавляем корень проекта в пути поиска модулей
# tests/ -> корень проекта
PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

from src.core.downloader import VideoDownloader
from src.core.transcriber import Transcriber
from src.core.translator import Translator
from src.core.synthesizer import TTSProcessor
from src.core.muxer import VideoMuxer

# Настраиваем красивые логи, чтобы видеть процесс
logging.basicConfig(
    level=logging.INFO, 
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger("VoxSync-Pipeline")

async def run_pipeline():
    print("\n" + "="*60)
    print("🚀 СТАРТ ПОЛНОГО ПАЙПЛАЙНА VOXSYNC")
    print("="*60)

    # --- НАСТРОЙКИ ЗАДАЧИ ---
    url = "https://www.youtube.com/watch?v=f0TrMH9s-VE"  # Me at the zoo (19 секунд)
    job_id = "test_job_002"
    target_lang = "ru" # Можно поменять на 'de', 'es', 'fr'
    # ------------------------

    try:
        # [ШАГ 1] Скачивание
        print(f"\n[1/5] 📥 Скачивание видео: {url}")
        dl = VideoDownloader()
        dl_result = dl.download(url, job_id=job_id)
        print(f"      ✅ Видео: {dl_result.video_path.name} | Аудио: {dl_result.audio_path.name}")

        # [ШАГ 2] Распознавание (Whisper) + Анализ пола (DSP)
        print("\n[2/5] 🎧 Распознавание речи и определение пола...")
        transcriber = Transcriber(model_name="small") # Используем small для скорости
        trans_result = transcriber.transcribe(dl_result.audio_path)
        
        # Печатаем оригинал для наглядности
        print("\n--- Оригинальный текст ---")
        for s in trans_result.segments[:3]:
            print(f"[{s.start:.1f}s - {s.end:.1f}s] ({s.gender}): {s.text}")

        # [ШАГ 3] Семантический перевод (LLM)
        print("\n[3/5] 🧠 Перевод с учетом контекста (LLM)...")
        translator = Translator(target_lang=target_lang)
        translated_segments = translator.translate_segments(trans_result.segments)
        
        print("\n--- Переведенный текст ---")
        for s in translated_segments[:3]:
            print(f"[{s.start:.1f}s - {s.end:.1f}s] ({s.gender}): {s.text}")

        # [ШАГ 4] Синтез речи (Edge-TTS) + Синхронизация (Элайнер)
        print("\n[4/5] 🗣️ Синтез и подгонка аудио (Time-stretching)...")
        tts = TTSProcessor(target_lang=target_lang)
        dubbed_audio_path = await tts.synthesize(translated_segments, dl_result.video_path.parent)
        print(f"      ✅ Аудио готово: {dubbed_audio_path.name}")

        # [ШАГ 5] Наложение звука на видео (Muxer)
        print("\n[5/5] 🎬 Сборка финального видео...")
        # По умолчанию заменяем оригинальную дорожку на дубляж,
        # чтобы не было эффекта «две речи одновременно».
        muxer = VideoMuxer(original_volume=0.15, dubbed_volume=1.5, mix_original=False)
        final_video_path = dl_result.video_path.parent / f"result_{target_lang}.mp4"
        
        muxer.mix(
            video_path=dl_result.video_path, 
            dubbed_audio_path=dubbed_audio_path, 
            output_path=final_video_path
        )

        print("\n" + "="*60)
        print(f"🎉 УСПЕХ! Пайплайн завершен.")
        print(f"📍 Открой файл и проверь результат: {final_video_path}")
        print("="*60)

    except Exception as e:
        logger.error(f"❌ ПАЙПЛАЙН ПРЕРВАН С ОШИБКОЙ: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(run_pipeline())