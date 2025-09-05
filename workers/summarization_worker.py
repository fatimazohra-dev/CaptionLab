from PyQt5.QtCore import QThread, pyqtSignal
import google.generativeai as genai

class GeminiSummarizationWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    summarization_complete = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, text_to_summarize, api_key):
        super().__init__()
        self.text_to_summarize = text_to_summarize
        self.api_key = api_key

    def run(self):
        try:
            self.progress_updated.emit(0, "Initializing Gemini...")
            genai.configure(api_key=self.api_key)
            model = genai.GenerativeModel('gemini-pro')
            
            self.progress_updated.emit(30, "Generating summary...")
            prompt = f"""Please provide a concise summary of the following text. 
            Focus on the main points and key information:
            
            {self.text_to_summarize}"""
            
            response = model.generate_content(prompt)
            summary = response.text
            
            self.progress_updated.emit(100, "Summary complete!")
            self.summarization_complete.emit(summary)
            
        except Exception as e:
            self.error_occurred.emit(str(e)) 