from PyQt5.QtCore import QThread, pyqtSignal
import whisper

DEFAULT_WHISPER_MODEL = "base"

class SubtitleWorker(QThread):
    progress_updated = pyqtSignal(int, str)  # Value, Text
    transcription_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, video_path, model_name=DEFAULT_WHISPER_MODEL, source_language=None):
        super().__init__()
        self.video_path = video_path
        self.model_name = model_name
        self.source_language = source_language

    def run(self):
        try:
            self.progress_updated.emit(0, "Loading Whisper model...")
            model = whisper.load_model(self.model_name)
            
            self.progress_updated.emit(20, "Transcribing audio...")
            result = model.transcribe(
                self.video_path,
                language=self.source_language,
                verbose=False
            )
            
            self.progress_updated.emit(90, "Formatting transcription...")
            formatted_result = self._format_transcription(result)
            
            self.progress_updated.emit(100, "Transcription complete!")
            self.transcription_complete.emit(formatted_result)
            
        except Exception as e:
            self.error_occurred.emit(str(e))

    def _format_transcription(self, result):
        return {
            'text': result['text'],
            'segments': result['segments'],
            'language': result['language']
        } 