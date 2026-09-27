from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)
@dataclass
class LanguageConfig:
    code: str #кодовое обозначение языков ru, de, ua, en
    name: str #имя языка
    male_voice: str
    female_voice: str

SUPPORTED_LANGUAGES = {
    "ru": LanguageConfig(
        code="ru",
        name="Russian",
        male_voice="ru-RU-DmitryNeural",
        female_voice="ru-RU-SvetlanaNeural",
    ),
    "en": LanguageConfig(
        code="en",
        name="English",
        male_voice="en-US-ChristopherNeural",
        female_voice="en-US-JennyNeural",
    ),
    "de": LanguageConfig(
        code="de",
        name="German",
        male_voice="de-DE-KillianNeural",
        female_voice="de-DE-AmalaNeural",
    ),
    "es": LanguageConfig(
        code="es",
        name="Spanish",
        male_voice="es-ES-AlvaroNeural",
        female_voice="es-ES-ElviraNeural",
    ),
    "fr": LanguageConfig(
        code="fr",
        name="French",
        male_voice="fr-FR-HenriNeural",
        female_voice="fr-FR-DeniseNeural",
    ),
    "it": LanguageConfig(
        code="it",
        name="Italian",
        male_voice="it-IT-DiegoNeural",
        female_voice="it-IT-ElsaNeural",
    ),
    "pt": LanguageConfig(
        code="pt",
        name="Portuguese",
        male_voice="pt-PT-DuarteNeural",
        female_voice="pt-PT-RaquelNeural",
    ),
    "pl": LanguageConfig(
        code="pl",
        name="Polish",
        male_voice="pl-PL-MarekNeural",
        female_voice="pl-PL-ZofiaNeural",
    ),
    "nl": LanguageConfig(
        code="nl",
        name="Dutch",
        male_voice="nl-NL-MaartenNeural",
        female_voice="nl-NL-FennaNeural",
    ),
    "tr": LanguageConfig(
        code="tr",
        name="Turkish",
        male_voice="tr-TR-AhmetNeural",
        female_voice="tr-TR-EmelNeural",
    ),
    "uk": LanguageConfig(
        code="uk",
        name="Ukrainian",
        male_voice="uk-UA-OstapNeural",
        female_voice="uk-UA-PolinaNeural",
    ),
    "zh": LanguageConfig(
        code="zh",
        name="Chinese",
        male_voice="zh-CN-YunxiNeural",
        female_voice="zh-CN-XiaoxiaoNeural",
    ),
    "ja": LanguageConfig(
        code="ja",
        name="Japanese",
        male_voice="ja-JP-KeitaNeural",
        female_voice="ja-JP-NanamiNeural",
    ),
    "ko": LanguageConfig(
        code="ko",
        name="Korean",
        male_voice="ko-KR-InJoonNeural",
        female_voice="ko-KR-SunHiNeural",
    ),
    "ar": LanguageConfig(
        code="ar",
        name="Arabic",
        male_voice="ar-SA-HamedNeural",
        female_voice="ar-SA-ZariyahNeural",
    ),
}

def get_language_config(lang_code: str) -> LanguageConfig:
    """
    Возвращает конфиг по коду языка.
    Если язык не найден, возвращает русский по умолчанию и пишет Warning.
    """
    lang_code = lang_code.lower()
    if lang_code not in SUPPORTED_LANGUAGES:
        logger.warning(f"Язык '{lang_code}' не поддерживается. Fallback на 'ru'.")
        return SUPPORTED_LANGUAGES["ru"]
    
    return SUPPORTED_LANGUAGES[lang_code]
    