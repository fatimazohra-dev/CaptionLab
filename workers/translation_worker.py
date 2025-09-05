from PyQt5.QtCore import QThread, pyqtSignal
from googletrans import Translator

class TranslationWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    translation_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, subtitle_data, target_language):
        super().__init__()
        self.subtitle_data = subtitle_data
        self.target_language = target_language
        self.translator = Translator()

    def map_whisper_to_google_lang_code(self, whisper_code):
        # Mapping des codes de langue Whisper vers les codes Google Translate
        language_mapping = {
            'en': 'en',
            'fr': 'fr',
            'es': 'es',
            'de': 'de',
            'it': 'it',
            'pt': 'pt',
            'nl': 'nl',
            'pl': 'pl',
            'ru': 'ru',
            'ja': 'ja',
            'ko': 'ko',
            'zh': 'zh-cn',
            'ar': 'ar',
            'hi': 'hi',
            'tr': 'tr'
        }
        return language_mapping.get(whisper_code, 'en')

    def run(self):
        try:
            translated_segments = []
            total_segments = len(self.subtitle_data['segments'])
            
            for i, segment in enumerate(self.subtitle_data['segments']):
                progress = int((i / total_segments) * 100)
                self.progress_updated.emit(progress, f"Translating segment {i+1}/{total_segments}")
                
                translated_text = self.translator.translate(
                    segment['text'],
                    dest=self.map_whisper_to_google_lang_code(self.target_language)
                ).text
                
                translated_segment = segment.copy()
                translated_segment['text'] = translated_text
                translated_segments.append(translated_segment)
            
            result = {
                'segments': translated_segments,
                'language': self.target_language
            }
            
            self.progress_updated.emit(100, "Translation complete!")
            self.translation_complete.emit(result)
            
        except Exception as e:
            self.error_occurred.emit(str(e)) 