import logging
import asyncio
import sys
import os
import torch
import soundfile as sf
from pathlib import Path

from src.core.transcriber import Segment
from src.core.aligner import AudioAligner
from src.core.languages import get_language_config

logger = logging.getLogger(__name__)

class TTSProcessor:
    """Локальный модуль генерации речи (Silero TTS)"""

    def __init__(self, target_lang: str = "ru"):
        self.lang_config = get_language_config(target_lang)
        self.aligner = AudioAligner()
        
        # Используем CPU (на Mac работает мгновенно)
        self.device = torch.device('cpu')
        
        # Состояние текущей загруженной модели
        self.current_model_lang = None
        self.model = None
        self.sample_rate = 48000

    def _load_model_if_needed(self):
        """Динамически загружает нужную модель, если язык поменялся в пайплайне"""
        target_lang = self.lang_config.code[:2] # 'ru', 'en', 'de' и т.д.
        
        # Если нужная модель уже в оперативной памяти — ничего не делаем
        if self.current_model_lang == target_lang and self.model is not None:
            return
            
        logger.info(f"Загрузка локальной нейросети Silero TTS для языка: {target_lang}...")
        
        # Конфигурация моделей Silero
        silero_models = {
            "ru": "v4_ru",
            "en": "v3_en",
            "de": "v3_de",
            "es": "v3_es",
            "fr": "v3_fr"
        }
        
        model_id = silero_models.get(target_lang)
        if not model_id:
            logger.warning(f"Язык {target_lang} не поддерживается Silero. Включаем русский.")
            target_lang = "ru"
            model_id = "v4_ru"
            
        # --- ВРЕМЕННОЕ РАЗРЕШЕНИЕ КОНФЛИКТА ИМЕН 'src' ---
        # 1. Сохраняем оригинальные пути поиска и кэш модулей вашего проекта
        original_sys_path = sys.path.copy()
        
        # Находим все модули вашего проекта (src и src.core, src.pipeline и т.д.)
        src_keys = [k for k in sys.modules.keys() if k == 'src' or k.startswith('src.')]
        original_src_modules = {k: sys.modules[k] for k in src_keys}
        
        # 2. Временно удаляем их из глобального кэша Python на время импорта
        for k in src_keys:
            del sys.modules[k]

        cwd = os.getcwd()
        sys.path = [p for p in sys.path if p != '' and p != cwd]
        
        try:
            # 3. Загружаем модель. Теперь Python гарантированно найдет папку src внутри Silero
            self.model, _ = torch.hub.load(
                repo_or_dir='snakers4/silero-models',
                model='silero_tts',
                language=target_lang,
                speaker=model_id,
                trust_repo=True
            )
        finally:
            # 4. ВОЗВРАЩАЕМ ВСЕ НА МЕСТО
            # Восстанавливаем оригинальные пути
            sys.path = original_sys_path
            
            # Удаляем то, что успел подгрузить Silero под именем 'src' во время импорта
            for k in list(sys.modules.keys()):
                if k == 'src' or k.startswith('src.'):
                    del sys.modules[k]
                    
            # Возвращаем модули вашего проекта обратно в кэш
            for k, v in original_src_modules.items():
                sys.modules[k] = v
        # -------------------------------------------------
        
        self.model.to(self.device)
        
        # Частота дискретизации (для v4_ru это 48000, для остальных 24000)
        self.sample_rate = 48000 if target_lang == "ru" else 24000
        self.current_model_lang = target_lang
        
        logger.info(f"✅ Локальная модель TTS ({target_lang}) успешно загружена в память!")

    def _get_speaker(self, gender: str) -> str:
        """Выбор голоса в зависимости от языка и пола"""
        lang = self.current_model_lang
        if lang == "ru":
            return "xenia" if gender == "female" else "aidar"
        elif lang == "en":
            return "en_11" if gender == "female" else "en_0"
        elif lang == "de":
            return "eva" if gender == "female" else "karlsson"
        elif lang == "es":
            return "es_1" if gender == "female" else "es_0"
        elif lang == "fr":
            return "fr_1" if gender == "female" else "fr_0"
        return "aidar"

    async def _generate_audio_file(self, text: str, speaker: str, output_path: Path):
        """Синхронная генерация аудио через PyTorch, обернутая в асинхронный вызов"""
        clean_text = text.strip()
        
        def run_tts():
            # Генерируем аудио-тензор
            audio_tensor = self.model.apply_tts(
                text=clean_text,
                speaker=speaker,
                sample_rate=self.sample_rate
            )
            # Сохраняем в WAV файл
            sf.write(str(output_path), audio_tensor.numpy(), self.sample_rate)

        # Запускаем в отдельном потоке, чтобы не вешать сервер FastAPI
        await asyncio.to_thread(run_tts)
    
    async def synthesize(self, segments: list[Segment], job_dir: Path) -> Path:
        # 1. Проверяем, нужно ли сменить модель (если пайплайн поменял язык)
        self._load_model_if_needed()
        
        temp_dir = job_dir / "segments"
        temp_dir.mkdir(exist_ok=True, parents=True)
        
        audio_paths = []
        valid_segments = []
        
        logger.info(f"Начинаю локальную генерацию {len(segments)} аудиофрагментов...")
        
        for i, seg in enumerate(segments):
            if not seg.text or not seg.text.strip():
                continue
            
            speaker = self._get_speaker(seg.gender)
            file_path = temp_dir / f"{i:04d}.wav"
            
            try:
                await self._generate_audio_file(seg.text, speaker, file_path)
                audio_paths.append(file_path)
                valid_segments.append(seg)
            except Exception as e:
                logger.error(f"❌ Ошибка локального TTS на сегменте {i} ('{seg.text}'): {e}")

        # Склеиваем все кусочки
        final_audio = self.aligner.align(valid_segments, audio_paths)
        
        output_path = job_dir / f"dubbed_audio_{self.lang_config.code}.mp3"
        final_audio.export(str(output_path), format="mp3")
        
        logger.info(f"Синтез аудиодорожки завершен: {output_path}")
        return output_path