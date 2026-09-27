import logging
from typing import List

try:
    from mlx_lm import load, generate
    MLX_AVAILABLE = True
except ImportError:
    MLX_AVAILABLE = False

from src.core.transcriber import Segment
from src.core.languages import get_language_config

logger = logging.getLogger(__name__)

class Translator: 
    """Модуль семантического перевода на базе локальной LLM с пофразовой контекстной точностью"""

    def __init__(self, target_lang: str = "ru"):
        self.lang_config = get_language_config(target_lang)

        if not MLX_AVAILABLE:
            raise ImportError("Не установлена библиотека mlx-lm. Выполните: pip install mlx-lm")
        
        self.model_path = "mlx-community/Qwen2.5-7B-Instruct-4bit"
        logger.info(f"Загрузка LLM ({self.lang_config.name}): {self.model_path}...")
        self.model, self.tokenizer = load(self.model_path)
        logger.info("Модель перевода готова.")

    def _create_prompt(self, current_text: str, context_text: str) -> str:
        """Динамический промпт для перевода ровно одной строки с учетом контекста"""
        return f"""<|im_start|>system
You are a professional subtitle translator.
Translate the following single line into {self.lang_config.name}.

Context of previous lines (for reference only, do NOT translate these):
{context_text}

CRITICAL RULES:
1. Translate ONLY the current line. Do NOT combine it with previous lines.
2. Output ONLY the translated text. Do NOT add any tags, quotes, explanations, or notes.
3. Keep the translation concise and matching the rhythm of the original line.
4. If the current line is already in {self.lang_config.name}, return it exactly as is.
<|im_end|>
<|im_start|>user
Current line to translate:
"{current_text}"
<|im_end|>
<|im_start|>assistant
"""
    
    def translate_segments(self, segments: List[Segment]) -> List[Segment]:
        if not segments:
            return []
        
        logger.info(f"Начинаю пофразовый контекстный перевод {len(segments)} сегментов на {self.lang_config.name}...")

        translated_segments = []
        context_history = []  # Хранит историю последних фраз для связности текста

        for i, seg in enumerate(segments):
            current_text = seg.text.strip()
            if not current_text:
                translated_segments.append(seg)
                continue

            # Собираем контекст из последних 3 переведенных фраз для сохранения нити разговора
            context_text = "\n".join(context_history[-3:]) if context_history else "(No previous context)"

            prompt = self._create_prompt(current_text, context_text)

            try:
                # Инференс одной фразы (очень быстрый, max_tokens ограничен)
                response = generate(
                    self.model,
                    self.tokenizer,
                    prompt=prompt,
                    max_tokens=128,
                    verbose=False,
                )

                # Очищаем перевод от кавычек и лишних пробелов
                translated_text = response.strip().strip('"').strip("'").strip()
                
                # Защита от редких галлюцинаций модели (когда она возвращает системный текст)
                if translated_text.lower().startswith("current line"):
                    translated_text = current_text

                translated_segments.append(
                    Segment(
                        start=seg.start,
                        end=seg.end,
                        text=translated_text,
                        speaker_id=seg.speaker_id,
                        gender=seg.gender,
                    )
                )
                
                # Добавляем в историю "Оригинал -> Перевод"
                context_history.append(f"{current_text} -> {translated_text}")

            except Exception as e:
                logger.error(f"Ошибка перевода сегмента {i}: {e}")
                translated_segments.append(seg) # Fallback на оригинал

        logger.info("Перевод успешно завершен.")
        return translated_segments