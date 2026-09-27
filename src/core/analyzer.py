import logging 
import librosa
import numpy as np

logger = logging.getLogger(__name__)

class AudioAnalyzer:
    """
    DSP-модуль для анализа физических характеристик аудио.
    Используется для классификации пола спикера по фундаментальной частоте (F0).
    """
    def __init__(self, pitch_threshold: float = 165.0):
        # Порог в 165 Гц. 
        # Обычно мужской голос: 85-155 Гц. Женский: 165-255 Гц.
        self.pitch_threshold = pitch_threshold

    def detect_gender(self, y: np.ndarray, sr: int, start: float, end: float) -> str:
        """
        Определяет пол по фрагменту загруженного аудио массива.
        
        Args:
            y: Аудиосигнал (numpy array)
            sr: Sample rate (частота дискретизации, обычно 16000)
            start: Начало фразы в секундах
            end: Конец фразы в секундах
        """
        duration = end - start

        #если фраза коротка, алгоритму не хватит данных

        if duration < 0.4:
            return "male"
        
        #переводим в секунды индексы массива
        start_sample = int(start * sr)
        end_sample = int(end * sr)

        #отрезаем нужный кусок звука (срез массива работает мгновенно)
        y_chunk = y[start_sample:end_sample]

        if len(y_chunk) == 0:
            return "male"
        
        try:
            # алгоритм pYIN: извлекает фундаментальную частоту (F0)
            # ищем частоты в диапазоне человеческого голоса (65 - 300 Гц)
            f0, voiced_flag, _ = librosa.pyin(
                y_chunk, 
                fmin=65, 
                fmax=300,
                sr=sr
            )

            # оставляем те моменты, где голос реально был (без тишины, её отсекаем)
            valid_f0 = f0[voiced_flag]

            if len(valid_f0) > 0:
                # медиана защищает от резких скачков (например, если человек чихнул или издал похожий высокий звук)
                median_pitch = np.nanmedian(valid_f0)

                logger.debug(f"[{start:.1f}s - {end:.1f}s] Pitch: {median_pitch:.1f} Hz")

                if median_pitch > self.pitch_threshold:
                    return "female"
                else:
                    return "male"
                
            else:
                return "male" # голос не найден, может быть как музыка, так и какие-то шумы
            
        except Exception as e:
            logger.warning(f"DSP Ошибка на отрезке {start}-{end}: {e}")
            return "male" 
