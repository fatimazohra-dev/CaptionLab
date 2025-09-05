import sys
import os
import tempfile
from pathlib import Path
import time
import json
import threading
import queue
import ssl
import subprocess
import winsound  # Pour les sons de notification

# Dictionnaire des traductions
TRANSLATIONS = {
    "English": {
        "upload_video": "Upload Video",
        "generate_subtitles": "Generate Subtitles",
        "summarize_video": "Summarize Video",
        "translate_subtitles": "Translate Subtitles",
        "export_current": "Export Current Tab",
        "source_language": "Source Language (Whisper):",
        "translate_to": "Translate to:",
        "model_label": "Whisper Model:",
        "original_subtitles": "Original Subtitles",
        "translated_subtitles": "Translated Subtitles",
        "video_summary": "Video Summary",
        "app_language": "Application Language:",
    },
    "Français": {
        "upload_video": "Importer une Vidéo",
        "generate_subtitles": "Générer les Sous-titres",
        "summarize_video": "Résumer la Vidéo",
        "translate_subtitles": "Traduire les Sous-titres",
        "export_current": "Exporter l'Onglet Actuel",
        "source_language": "Langue Source (Whisper) :",
        "translate_to": "Traduire vers :",
        "model_label": "Modèle Whisper :",
        "original_subtitles": "Sous-titres Originaux",
        "translated_subtitles": "Sous-titres Traduits",
        "video_summary": "Résumé de la Vidéo",
        "app_language": "Langue de l'Application :",
    },
    "العربية": {
        "upload_video": "تحميل الفيديو",
        "generate_subtitles": "إنشاء الترجمة",
        "summarize_video": "تلخيص الفيديو",
        "translate_subtitles": "ترجمة الترجمة",
        "export_current": "تصدير التبويب الحالي",
        "source_language": "اللغة المصدر (Whisper):",
        "translate_to": "الترجمة إلى:",
        "model_label": "نموذج Whisper:",
        "original_subtitles": "الترجمة الأصلية",
        "translated_subtitles": "الترجمة المترجمة",
        "video_summary": "ملخص الفيديو",
        "app_language": "لغة التطبيق:",
    }
}

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QPushButton, QLabel, QVBoxLayout, QHBoxLayout,
    QWidget, QFileDialog, QComboBox, QProgressBar, QTextEdit, QTabWidget,
    QScrollArea, QFrame, QSplitter, QListWidget, QMessageBox, QSlider,
    QStyleFactory, QToolButton, QAction, QMenuBar, QMenu, QStatusBar,
    QGridLayout, QSpinBox, QSizePolicy
)
from PyQt5.QtGui import QPixmap, QImage, QFont, QIcon, QColor, QPalette, QFontDatabase
from PyQt5.QtCore import Qt, QTimer, QThread, pyqtSignal, QSize, QUrl, QEvent

import vlc
import whisper # Ensure this is openai-whisper
from deep_translator import GoogleTranslator

import google.generativeai as genai
from dotenv import load_dotenv

# Sumy imports
from sumy.parsers.plaintext import PlaintextParser
from sumy.nlp.tokenizers import Tokenizer
from sumy.summarizers.lsa import LsaSummarizer as SummarizerLSA
from sumy.nlp.stemmers import Stemmer
from sumy.utils import get_stop_words
import nltk

# --- Constantes ---
APP_NAME = "CAPTION LAB"
APP_VERSION = "1.3.0" # Version bump for new features/fixes
DEFAULT_WHISPER_MODEL = "base"
WHISPER_MODELS = ["tiny", "base", "small", "medium", "large"]
DEFAULT_SUMMARY_SENTENCES = 5

# --- Worker Threads ---
class SubtitleWorker(QThread):
    progress_updated = pyqtSignal(int, str) # Value, Text
    transcription_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, video_path, model_name=DEFAULT_WHISPER_MODEL, source_language=None):
        super().__init__()
        self.video_path = video_path
        self.model_name = model_name
        self.source_language = source_language
        self.model = None

    def run(self):
        try:
            self.progress_updated.emit(5, f"Loading Whisper model '{self.model_name}'...")
            try:
                self.model = whisper.load_model(self.model_name)
                self.progress_updated.emit(30, f"Model '{self.model_name}' loaded.")
            except Exception as e:
                self.error_occurred.emit(f"Error loading model '{self.model_name}': {str(e)}. RAM/VRAM issue?")
                return

            self.progress_updated.emit(35, f"Transcribing with '{self.model_name}' model...")
            transcribe_args = {"audio": self.video_path, "fp16": False} # fp16=False for broader CPU compatibility
            if self.source_language and self.source_language.lower() != "auto":
                transcribe_args["language"] = self.source_language
            
            # Provide progress updates from Whisper if possible (not directly supported by standard transcribe)
            # For now, we'll just estimate stages.
            
            result = self.model.transcribe(**transcribe_args) # This is blocking
            self.progress_updated.emit(90, "Finalizing transcription...")

            formatted_result = self._format_transcription(result)
            self.progress_updated.emit(100, "Transcription complete!")
            self.transcription_complete.emit(formatted_result)

        except Exception as e:
            self.error_occurred.emit(f"Error during transcription: {str(e)}")
            self.progress_updated.emit(0, "Transcription failed.")


    def _format_transcription(self, result):
        segments = []
        if result and "segments" in result:
            for segment in result["segments"]:
                segments.append({
                    "id": len(segments) + 1,
                    "start": segment.get("start", 0),
                    "end": segment.get("end", 0),
                    "text": segment.get("text", "").strip()
                })
        return {
            "text": result.get("text", "") if result else "",
            "segments": segments,
            "language": result.get("language", "unknown") if result else "unknown"
        }

class TranslationWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    translation_complete = pyqtSignal(dict)
    error_occurred = pyqtSignal(str)

    def __init__(self, subtitle_data, target_language):
        super().__init__()
        self.subtitle_data = subtitle_data
        self.target_language = target_language

    def map_whisper_to_google_lang_code(self, whisper_code):
        # Mapping des codes de langue Whisper vers les codes Google Translate
        mapping = {
            "zh": "zh-CN",  # Chinois simplifié par défaut
            "zh-cn": "zh-CN",
            "zh-tw": "zh-TW",
            "ko": "ko",
            "ja": "ja",
            "en": "en",
            "fr": "fr",
            "de": "de",
            "es": "es",
            "it": "it",
            "pt": "pt",
            "nl": "nl",
            "ru": "ru",
            "ar": "ar",
            "hi": "hi",
            "auto": "auto"
        }
        return mapping.get(whisper_code.lower(), "auto")

    def run(self):
        try:
            # Obtenir et mapper le code de langue source
            source_lang = self.subtitle_data.get("language", "auto")
            source_lang = self.map_whisper_to_google_lang_code(source_lang)
            
            self.progress_updated.emit(10, f"Translating from '{source_lang}' to '{self.target_language}'...")
            
            try:
                translator = GoogleTranslator(source=source_lang, target=self.target_language)
            except Exception as e:
                # Si la langue source pose problème, essayer avec 'auto'
                self.error_occurred.emit(f"Warning: Using auto-detection instead of {source_lang}")
                translator = GoogleTranslator(source='auto', target=self.target_language)
            
            translated_segments = []
            if not self.subtitle_data or "segments" not in self.subtitle_data:
                self.error_occurred.emit("No segments found to translate.")
                self.progress_updated.emit(100, "Translation failed: No segments.")
                self.translation_complete.emit({"text": "", "segments": [], "language": self.target_language})
                return

            total_segments = len(self.subtitle_data["segments"])
            if total_segments == 0:
                self.progress_updated.emit(100, "No segments to translate.")
                self.translation_complete.emit({"text": "", "segments": [], "language": self.target_language})
                return

            for i, segment in enumerate(self.subtitle_data["segments"]):
                try:
                    current_progress = int(10 + ((i + 1) / total_segments) * 80)
                    self.progress_updated.emit(current_progress, f"Translating segment {i+1}/{total_segments}...")
                    
                    text_to_translate = segment.get("text", "").strip()
                    if text_to_translate:
                        translated_text = translator.translate(text_to_translate)
                    else:
                        translated_text = ""
                    
                    translated_segments.append({
                        "id": segment.get("id"),
                        "start": segment.get("start"),
                        "end": segment.get("end"),
                        "text": translated_text
                    })
                except Exception as e:
                    self.error_occurred.emit(f"Warning: Error translating segment {i+1}: {str(e)}")
                    translated_segments.append({
                        "id": segment.get("id"),
                        "start": segment.get("start"),
                        "end": segment.get("end"),
                        "text": text_to_translate  # Garder le texte original en cas d'erreur
                    })

            self.progress_updated.emit(95, "Finalizing translation...")
            
            # Traduire le texte complet si disponible
            full_text = self.subtitle_data.get("text", "")
            if full_text.strip():
                try:
                    translated_full_text = translator.translate(full_text)
                except:
                    # En cas d'erreur, concaténer les segments traduits
                    translated_full_text = " ".join([s['text'] for s in translated_segments if s.get('text')])
            else:
                translated_full_text = " ".join([s['text'] for s in translated_segments if s.get('text')])

            translated_data = {
                "text": translated_full_text,
                "segments": translated_segments,
                "language": self.target_language
            }
            
            self.progress_updated.emit(100, "Translation complete!")
            self.translation_complete.emit(translated_data)

        except Exception as e:
            self.error_occurred.emit(f"Error during translation: {str(e)}")
            self.progress_updated.emit(0, "Translation failed.")


class GeminiSummarizationWorker(QThread):
    progress_updated = pyqtSignal(int, str)
    summarization_complete = pyqtSignal(str)
    error_occurred = pyqtSignal(str)

    def __init__(self, text_to_summarize, api_key):
        super().__init__()
        self.text_to_summarize = text_to_summarize
        self.api_key = api_key
        self.model = None

    def run(self):
        try:
            if not self.text_to_summarize or not self.text_to_summarize.strip():
                self.error_occurred.emit("No text provided for summarization.")
                self.summarization_complete.emit("")
                self.progress_updated.emit(0, "Summarization failed: No text.")
                return

            if not self.api_key:
                self.error_occurred.emit("Gemini API key not found. Please add it to your .env file.")
                self.summarization_complete.emit("")
                self.progress_updated.emit(0, "Summarization failed: API key missing.")
                return

            self.progress_updated.emit(10, "Initializing Gemini model...")
            genai.configure(api_key=self.api_key)
            # Using gemini-1.5-flash for potentially faster summarization
            self.model = genai.GenerativeModel('gemini-2.0-flash')
            self.progress_updated.emit(30, "Model initialized.")

            self.progress_updated.emit(40, "Generating summary...")
            prompt = f"""Summarize the following text:

{self.text_to_summarize}"""
            
            response = self.model.generate_content(prompt)
            summary_text = response.text

            self.progress_updated.emit(100, "Summarization complete!")
            self.summarization_complete.emit(summary_text)

        except Exception as e:
            self.error_occurred.emit(f"Error during Gemini summarization: {str(e)}")
            self.summarization_complete.emit("")
            self.progress_updated.emit(0, "Summarization failed.")

# --- VideoPlayer Class (Updated Section) ---
class VideoPlayer(QWidget):
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        vlc_options = ['--no-xlib', '--quiet', '--ignore-config']
        self.instance = vlc.Instance(vlc_options)
        self.player = self.instance.media_player_new()
        self.current_subtitle_text = ""
        self.subtitles = [] # For the manual overlay label
        self.subtitle_data_for_vlc = None # Data dict for currently loaded VLC subs
        self.subtitle_timer = QTimer(self)
        self.subtitle_timer.timeout.connect(self.update_subtitle_display)
        self.is_muted = False
        self.previous_volume = 70
        self.is_fullscreen = False  # Track fullscreen state
        self.normal_geometry = None  # Store normal window geometry
        self.init_ui()
        self.update_timer = QTimer(self)
        self.update_timer.timeout.connect(self.update_position_and_volume)
        self.update_timer.start(100)
        
        # Activer le focus pour recevoir les événements clavier
        self.setFocusPolicy(Qt.StrongFocus)
        self.video_widget.setFocusPolicy(Qt.StrongFocus)
        self.installEventFilter(self)
        self.video_widget.installEventFilter(self)

    def _rebuild_controls_layout(self, layout, items_ltr, direction):
        # Clear existing items from layout
        while layout.count():
            item = layout.takeAt(0)
            if item.widget():
                item.widget().setParent(None) # Crucial to allow re-adding
            # Spacers and other layout items don't need explicit deletion beyond takeAt

        effective_items = items_ltr
        if direction == Qt.RightToLeft:
            effective_items = list(reversed(items_ltr))

        for item_data in effective_items:
            item, item_type = item_data # Expects (item, type_string)

            if item_type == 'widget':
                layout.addWidget(item)
            elif item_type == 'spacing':
                layout.addSpacing(item) # item here is the size
            elif item_type == 'stretch':
                layout.addStretch(item) # item here is the stretch factor

    def set_layout_direction_for_controls(self, direction):
        if hasattr(self, 'controls_layout') and hasattr(self, 'normal_control_items_ltr'):
            self._rebuild_controls_layout(self.controls_layout, self.normal_control_items_ltr, direction)

        if self.is_fullscreen and hasattr(self, 'fs_controls_layout') and hasattr(self, 'fullscreen_control_items_ltr'):
            self._rebuild_controls_layout(self.fs_controls_layout, self.fullscreen_control_items_ltr, direction)

    def init_ui(self):
        layout = QVBoxLayout()
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.video_widget = QWidget()
        self.video_widget.setStyleSheet("background-color: #101010;")
        self.video_widget.setMinimumSize(320, 180)

        # Create controls widget with object name for identification
        controls_widget = QWidget()
        controls_widget.setObjectName("controls_widget")
        self.controls_layout = QHBoxLayout(controls_widget) # Store as instance member
        self.controls_layout.setContentsMargins(10, 8, 10, 8)
        self.controls_layout.setSpacing(8)

        self.play_button = QToolButton()
        self.play_button.setIcon(self.get_icon("play.png", "media-playback-start"))
        self.play_button.setIconSize(QSize(22, 22))
        self.play_button.setToolTip("Play/Pause (Space)")
        self.play_button.setStyleSheet("QToolButton { background-color: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 6px; padding: 8px; } QToolButton:hover { background-color: #3a3a3a; border-color: #4a4a4a; } QToolButton:pressed { background-color: #2196F3; border-color: #1E88E5; }")
        self.play_button.clicked.connect(self.toggle_play)

        self.subtitle_button = QToolButton()
        self.subtitle_button.setIcon(self.get_icon("subtitle.png", "document-edit"))
        self.subtitle_button.setIconSize(QSize(22, 22))
        self.subtitle_button.setToolTip("Toggle Subtitles")
        self.subtitle_button.setStyleSheet("QToolButton { background-color: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 6px; padding: 8px; } QToolButton:hover { background-color: #3a3a3a; border-color: #4a4a4a; } QToolButton:pressed { background-color: #2196F3; border-color: #1E88E5; }")
        self.subtitle_button.clicked.connect(self.toggle_subtitles)

        self.mute_button = QToolButton()
        self.mute_button.setIcon(self.get_icon("high-volume.png", "audio-volume-high"))
        self.mute_button.setIconSize(QSize(22, 22))
        self.mute_button.setToolTip("Mute/Unmute (M)")
        self.mute_button.setStyleSheet("QToolButton { background-color: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 6px; padding: 8px; } QToolButton:hover { background-color: #3a3a3a; border-color: #4a4a4a; } QToolButton:pressed { background-color: #2196F3; border-color: #1E88E5; }")
        self.mute_button.clicked.connect(self.toggle_mute)

        # Add fullscreen button
        self.fullscreen_button = QToolButton()
        self.fullscreen_button.setIcon(self.get_icon("fullscreen.png", "view-fullscreen"))
        self.fullscreen_button.setIconSize(QSize(22, 22))
        self.fullscreen_button.setToolTip("Toggle Fullscreen (F)")
        self.fullscreen_button.setStyleSheet("QToolButton { background-color: #2a2a2a; border: 1px solid #3a3a3a; border-radius: 6px; padding: 8px; } QToolButton:hover { background-color: #3a3a3a; border-color: #4a4a4a; } QToolButton:pressed { background-color: #2196F3; border-color: #1E88E5; }")
        self.fullscreen_button.clicked.connect(self.toggle_fullscreen)

        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setRange(0, 100)
        self.volume_slider.setValue(self.previous_volume)
        self.volume_slider.setToolTip("Volume")
        self.volume_slider.setMaximumWidth(120)
        self.volume_slider.valueChanged.connect(self.set_volume)
        self.volume_slider.setStyleSheet("QSlider::groove:horizontal { border: none; height: 6px; background: #3a3a3a; margin: 0px; border-radius: 3px; } QSlider::handle:horizontal { background: #2196F3; border: 1px solid #1E88E5; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; } QSlider::sub-page:horizontal { background: #2196F3; border-radius: 3px; }")

        self.time_label = QLabel("00:00 / 00:00")
        self.time_label.setStyleSheet("color: #e0e0e0; font-size: 12px; font-weight: 500;")
        self.time_label.setFixedWidth(100)

        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setRange(0, 0)
        self.position_slider.sliderMoved.connect(self.set_position_from_slider)
        self.position_slider.sliderPressed.connect(self.player.pause)
        self.position_slider.sliderReleased.connect(self.player.play)
        self.position_slider.setStyleSheet("QSlider::groove:horizontal { border: none; height: 6px; background: #3a3a3a; margin: 0px; border-radius: 3px; } QSlider::handle:horizontal { background: #2196F3; border: 1px solid #1E88E5; width: 16px; height: 16px; margin: -5px 0; border-radius: 8px; } QSlider::sub-page:horizontal { background: #2196F3; border-radius: 3px; }")

        # Define LTR order of control items
        self.normal_control_items_ltr = [
            (self.play_button, 'widget'),
            (self.position_slider, 'widget'),
            (self.time_label, 'widget'),
            (10, 'spacing'), # spacer
            (self.mute_button, 'widget'),
            (self.volume_slider, 'widget'),
            (10, 'spacing'), # spacer
            (self.subtitle_button, 'widget'),
            (self.fullscreen_button, 'widget'),
        ]
        
        # Initial population of the controls layout
        # The direction will be set correctly by MainWindow's initial language change trigger
        app_instance = QApplication.instance()
        initial_direction = app_instance.layoutDirection() if app_instance else Qt.LeftToRight
        self._rebuild_controls_layout(self.controls_layout, self.normal_control_items_ltr, initial_direction)

        controls_widget.setStyleSheet("background-color: #252525; border-top: 1px solid #3a3a3a;")
        controls_widget.setFixedHeight(50)

        self.subtitle_label = QLabel("")
        self.subtitle_label.setAlignment(Qt.AlignCenter)
        self.subtitle_label.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 0.7);
                color: #ffffff;
                padding: 10px;
                border-radius: 5px;
                font-weight: bold;
                filter: drop-shadow(1px 1px 2px black);
            }
        """)
        self.subtitle_label.setWordWrap(True)
        font = QFont("Arial", 16, QFont.Bold)
        self.subtitle_label.setFont(font)
        self.subtitle_label.hide()

        layout.addWidget(self.video_widget, 1)
        layout.addWidget(self.subtitle_label)
        layout.addWidget(controls_widget)
        self.setLayout(layout)

    def get_icon(self, icon_name, fallback_theme="application-default-icon"):
        base_path = getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__)))
        icon_path = os.path.join(base_path, "icons", icon_name)
        if os.path.exists(icon_path):
            return QIcon(icon_path)
        return QIcon.fromTheme(fallback_theme)

    def set_video(self, video_path):
        if not os.path.exists(video_path):
            self.error_occurred.emit(f"File not found: {video_path}")
            return
        try:
            # Arrêter la lecture en cours si elle existe
            if self.player.is_playing():
                self.player.stop()
            
            # Créer le média avec le chemin absolu
            video_path = os.path.abspath(video_path)
            if sys.platform == "win32":
                media = self.instance.media_new(video_path)
            else:
                media_uri = Path(video_path).resolve().as_uri()
                media = self.instance.media_new(media_uri)

            self.player.set_media(media)
            
            # S'assurer que le widget est visible
            if not self.video_widget.isVisible():
                self.video_widget.show()
            
            # Intégrer VLC dans le widget
            self._embed_vlc()
            
            # Démarrer la lecture après un court délai
            QTimer.singleShot(100, self.player.play)
            self.play_button.setIcon(self.get_icon("pause.png", "media-playback-pause"))
            
            # Mettre à jour la durée après un délai
            QTimer.singleShot(600, self.update_duration)
            
            # Définir le volume
            self.set_volume(self.volume_slider.value())
            
        except Exception as e:
            self.error_occurred.emit(f"Error loading video: {str(e)}")

    def _embed_vlc(self):
        """Embed VLC player in the video widget"""
        try:
            if self.player and self.video_widget:
                handle = self.video_widget.winId()
                if handle:
                    # Désactiver temporairement le mode plein écran de VLC
                    self.player.set_fullscreen(False)
                    
                    # Intégrer VLC dans le widget
                    if sys.platform == "win32":
                        self.player.set_hwnd(int(handle))
                    elif sys.platform.startswith('linux'):
                        self.player.set_xwindow(int(handle))
                    elif sys.platform == "darwin":
                        self.player.set_nsobject(int(handle))
                    
                    # Configurer l'échelle vidéo
                    self.player.video_set_scale(0)  # Auto scale
                    
                    # Forcer la mise à jour de la taille
                    self.video_widget.update()
                    
                    # Si en mode plein écran, maximiser la fenêtre
                    if self.is_fullscreen and hasattr(self, 'fullscreen_container'):
                        self.fullscreen_container.showFullScreen()
                else:
                    QTimer.singleShot(100, self._embed_vlc)
        except Exception as e:
            self.error_occurred.emit(f"Error embedding video: {str(e)}")
            QTimer.singleShot(100, self._embed_vlc)

    def toggle_play(self):
        if self.player.is_playing():
            self.player.pause()
            self.subtitle_timer.stop()
            icon = self.get_icon("play.png", "media-playback-start")
            self.play_button.setIcon(icon)
            # Update fullscreen play button icon if it exists
            if self.is_fullscreen and hasattr(self, 'fs_controls'):
                self.fs_controls['play_button'].setIcon(icon)
        else:
            if self.player.get_media() is None and hasattr(self.parent(), 'video_path') and self.parent().video_path:
                self.set_video(self.parent().video_path)
            elif self.player.get_media():
                self.player.play()
                self.subtitle_timer.start(100)
                icon = self.get_icon("pause.png", "media-playback-pause")
                self.play_button.setIcon(icon)
                # Update fullscreen play button icon if it exists
                if self.is_fullscreen and hasattr(self, 'fs_controls'):
                    self.fs_controls['play_button'].setIcon(icon)

    def update_position_and_volume(self):
        if not self.player or self.player.get_media() is None:
            return

        # Get current media position
        media_pos = self.player.get_position()
        
        # Update position slider
        if media_pos >= 0:
            if self.is_fullscreen and hasattr(self, 'fs_controls'):
                slider = self.fs_controls['position_slider']
                if not slider.isSliderDown():
                    slider.blockSignals(True)
                    slider.setValue(int(media_pos * slider.maximum()))
                    slider.blockSignals(False)
            if not self.is_fullscreen and not self.position_slider.isSliderDown():
                self.position_slider.blockSignals(True)
                self.position_slider.setValue(int(media_pos * self.position_slider.maximum()))
                self.position_slider.blockSignals(False)

        # Update time label
        current_time_ms = self.player.get_time()
        duration_ms = self.player.get_length()
        time_text = f"{self.format_time(current_time_ms)} / {self.format_time(duration_ms)}"
        
        if self.is_fullscreen and hasattr(self, 'fs_controls'):
            self.fs_controls['time_label'].setText(time_text)
        else:
            self.time_label.setText(time_text)

        # Update volume slider and mute button
        if not self.is_muted:
            current_volume = self.player.audio_get_volume()
            if self.is_fullscreen and hasattr(self, 'fs_controls'):
                slider = self.fs_controls['volume_slider']
                if not slider.isSliderDown() and slider.value() != current_volume:
                    slider.blockSignals(True)
                    slider.setValue(current_volume)
                    slider.blockSignals(False)
            elif not self.is_fullscreen and not self.volume_slider.isSliderDown():
                if self.volume_slider.value() != current_volume:
                    self.volume_slider.blockSignals(True)
                    self.volume_slider.setValue(current_volume)
                    self.volume_slider.blockSignals(False)
            
            # Update mute button icon based on current volume
            self.update_mute_button_icon(current_volume)

    def update_duration(self):
        duration = self.player.get_length()
        if duration > 0:
            self.position_slider.setRange(0, 1000)
            self.time_label.setText(f"00:00 / {self.format_time(duration)}")
        else:
            self.position_slider.setRange(0,0)
            self.time_label.setText("00:00 / --:--")
            QTimer.singleShot(500, self.update_duration) # Retry if duration not ready

    def set_position_from_slider(self, value):
        if self.player.get_media() and self.position_slider.maximum() > 0:
            self.player.set_position(value / float(self.position_slider.maximum()))

    def set_volume(self, value):
        if self.player.audio_set_volume(value) == 0:
            if value == 0:
                if not self.is_muted: self.toggle_mute(force_mute=True)
            else:
                if self.is_muted: self.toggle_mute(force_unmute=True)
                self.previous_volume = value
        self.update_mute_button_icon(self.player.audio_get_volume())

    def toggle_mute(self, force_mute=False, force_unmute=False):
        if force_mute: self.is_muted = False
        if force_unmute: self.is_muted = True
        current_volume = self.player.audio_get_volume()
        if self.is_muted:
            vol_to_set = self.previous_volume if self.previous_volume > 0 else 70
            self.player.audio_set_volume(vol_to_set)
            self.volume_slider.setValue(vol_to_set)
            if self.is_fullscreen and hasattr(self, 'fs_controls'):
                self.fs_controls['volume_slider'].setValue(vol_to_set)
            self.is_muted = False
        else:
            if current_volume > 0: self.previous_volume = current_volume
            self.player.audio_set_volume(0)
            self.volume_slider.setValue(0)
            if self.is_fullscreen and hasattr(self, 'fs_controls'):
                self.fs_controls['volume_slider'].setValue(0)
            self.is_muted = True
        self.update_mute_button_icon(self.player.audio_get_volume())

    def update_mute_button_icon(self, volume):
        if self.is_muted or volume == 0:
            icon = self.get_icon("volume-muted.png", "audio-volume-muted")
        elif volume < 33:
            icon = self.get_icon("volume-low.png", "audio-volume-low")
        elif volume < 66:
            icon = self.get_icon("volume-medium.png", "audio-volume-medium")
        else:
            icon = self.get_icon("volume-high.png", "audio-volume-high")
        
        self.mute_button.setIcon(icon)
        # Update fullscreen mute button icon if it exists
        if self.is_fullscreen and hasattr(self, 'fs_controls'):
            self.fs_controls['mute_button'].setIcon(icon)

    def format_time(self, milliseconds):
        if milliseconds < 0: milliseconds = 0
        seconds = int(milliseconds / 1000)
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def set_subtitles_for_overlay(self, segments): # Renamed for clarity
        self.subtitles = segments if segments else []

    def update_subtitle_display(self): # For the QWidget overlay
        if not self.subtitles or not self.player.is_playing():
            self.subtitle_label.setText("")
            self.subtitle_label.hide()
            return
        current_time_sec = self.player.get_time() / 1000.0
        current_text = ""
        for segment in self.subtitles:
            if segment.get("start", 0) <= current_time_sec <= segment.get("end", float('inf')):
                current_text = segment.get("text", "")
                break
        if current_text != self.current_subtitle_text:
            self.current_subtitle_text = current_text
            self.subtitle_label.setText(current_text)
            self.subtitle_label.setVisible(bool(current_text))

    def toggle_subtitles(self):
        """Toggle subtitles visibility"""
        if not self.player:
            self.error_occurred.emit("Player not initialized")
            return

        # Check if we have any subtitle data
        has_vlc_subs = self.player.video_get_spu_count() > 0
        has_overlay_subs = bool(self.subtitles)

        if not has_vlc_subs and not has_overlay_subs:
            # Try to load subtitles if available from parent
            if hasattr(self.parent(), 'translated_data') and self.parent().translated_data:
                self.load_preferred_subtitles_to_vlc()
                self.error_occurred.emit("Loading available subtitles...")
                return
            elif hasattr(self.parent(), 'subtitle_data') and self.parent().subtitle_data:
                self.load_preferred_subtitles_to_vlc()
                self.error_occurred.emit("Loading available subtitles...")
                return
            else:
                self.error_occurred.emit("No subtitles available - Generate subtitles first")
                return

        # Toggle VLC subtitles if available
        if has_vlc_subs:
            current_spu = self.player.video_get_spu()
            if current_spu == -1:
                self.player.video_set_spu(0)
                self.subtitle_label.hide()  # Hide overlay if showing
                self.error_occurred.emit("Subtitles enabled")
            else:
                self.player.video_set_spu(-1)
                # If we have overlay subs, show them instead
                if has_overlay_subs:
                    self.subtitle_label.show()
                    if not self.subtitle_timer.isActive():
                        self.subtitle_timer.start(100)
                    self.error_occurred.emit("Switched to overlay subtitles")
                else:
                    self.error_occurred.emit("Subtitles disabled")
        # Toggle overlay subtitles if no VLC subs
        elif has_overlay_subs:
            if self.subtitle_label.isVisible():
                self.subtitle_label.hide()
                self.subtitle_timer.stop()
                self.error_occurred.emit("Subtitles disabled")
            else:
                self.subtitle_label.show()
                if not self.subtitle_timer.isActive():
                    self.subtitle_timer.start(100)
                self.error_occurred.emit("Subtitles enabled")

    def load_preferred_subtitles_to_vlc(self):
        """Loads translated subtitles to VLC if available, otherwise original."""
        data_to_load = None
        load_message = ""

        # Prioritize translated data if it exists and has segments
        if hasattr(self.parent(), 'translated_data') and self.parent().translated_data and \
           self.parent().translated_data.get("segments"):
            data_to_load = self.parent().translated_data
            load_message = "Loading translated subtitles to VLC..."
        # Fallback to original data if translated is not suitable or doesn't exist
        elif hasattr(self.parent(), 'subtitle_data') and self.parent().subtitle_data and \
             self.parent().subtitle_data.get("segments"):
            data_to_load = self.parent().subtitle_data
            load_message = "Loading original subtitles to VLC..."
        
        if data_to_load:
            self.error_occurred.emit(load_message) # Show status message
            self._execute_load_subtitles_to_vlc(data_to_load)
        else:
            self.error_occurred.emit("No suitable subtitles available to load into VLC.")


    def _execute_load_subtitles_to_vlc(self, subtitle_data_dict):
        if not subtitle_data_dict or not subtitle_data_dict.get("segments"):
            self.error_occurred.emit("No subtitle segments provided to load.")
            return
        if not self.player.get_media():
            self.error_occurred.emit("Load a video first before loading subtitles.")
            return

        # Cleanup previous temp file if managed by MainWindow
        if hasattr(self.parent(), 'current_srt_for_vlc') and self.parent().current_srt_for_vlc:
            if os.path.exists(self.parent().current_srt_for_vlc):
                try:
                    os.remove(self.parent().current_srt_for_vlc)
                    self.parent().current_srt_for_vlc = None
                except OSError as e:
                    print(f"Could not remove previous temp SRT: {e}")
        
        temp_srt_path_local = ""
        try:
            # Create temp file with absolute path
            temp_dir = os.path.dirname(os.path.abspath(self.parent().video_path))
            temp_srt_path_local = os.path.join(temp_dir, f"temp_subtitles_{int(time.time())}.srt")
            
            with open(temp_srt_path_local, 'w', encoding='utf-8', errors='replace') as srt_file:
                for i, segment in enumerate(subtitle_data_dict["segments"]):
                    srt_file.write(f"{i + 1}\n")
                    start_time = self.format_srt_timestamp(segment.get("start", 0))
                    end_time = self.format_srt_timestamp(segment.get("end", 0))
                    srt_file.write(f"{start_time} --> {end_time}\n")
                    srt_file.write(f"{segment.get('text', '')}\n\n")

            if hasattr(self.parent(), 'current_srt_for_vlc'):
                self.parent().current_srt_for_vlc = temp_srt_path_local

            # Stop and restart the player to ensure subtitle loading
            was_playing = self.player.is_playing()
            current_time = self.player.get_time()
            self.player.stop()
            
            # Create new media with subtitle
            media_uri = Path(self.parent().video_path).resolve().as_uri()
            media = self.instance.media_new(media_uri)
            media.add_options(f":sub-file={temp_srt_path_local}")
            self.player.set_media(media)
            
            # Restore playback state
            self._embed_vlc()
            self.player.play()
            if current_time > 0:
                self.player.set_time(current_time)
            if not was_playing:
                self.player.pause()
            
            self.error_occurred.emit("Subtitles loaded successfully.")
            
        except Exception as e:
            self.error_occurred.emit(f"Error loading subtitles to VLC: {str(e)}")
            if temp_srt_path_local and os.path.exists(temp_srt_path_local):
                try:
                    os.remove(temp_srt_path_local)
                except:
                    pass
            if hasattr(self.parent(), 'current_srt_for_vlc'):
                self.parent().current_srt_for_vlc = None


    def format_srt_timestamp(self, seconds_float): # Duplicated from MainWindow, keep one. This is fine here.
        if not isinstance(seconds_float, (int, float)) or seconds_float < 0: seconds_float = 0
        total_seconds = int(seconds_float)
        milliseconds = int((seconds_float - total_seconds) * 1000)
        hours = total_seconds // 3600
        minutes = (total_seconds % 3600) // 60
        seconds = total_seconds % 60
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    def stop_player(self):
        if self.player:
            if self.player.is_playing(): self.player.stop()
            self.player.set_media(None)
        if self.subtitle_timer: self.subtitle_timer.stop()
        if self.update_timer: self.update_timer.stop()

    def eventFilter(self, obj, event):
        """Filter events for keyboard shortcuts"""
        if event.type() == QEvent.KeyPress:
            key = event.key()
            if key == Qt.Key_F:
                self.toggle_fullscreen()
                return True
            elif key == Qt.Key_Space:
                self.toggle_play()
                return True
            elif key == Qt.Key_M:
                self.toggle_mute()
                return True
            elif key == Qt.Key_Escape and self.is_fullscreen:
                self.toggle_fullscreen()
                return True
        return super().eventFilter(obj, event)

    def toggle_fullscreen(self):
        """Toggle fullscreen mode with video taking up the entire screen"""
        if not self.is_fullscreen:
            # Store current geometry and parent
            self.normal_geometry = self.parent().geometry()
            self.normal_parent = self.parent()
            
            # Create a new fullscreen window that will contain everything
            self.fullscreen_container = QWidget()
            self.fullscreen_container.setWindowFlags(Qt.Window | Qt.FramelessWindowHint)
            self.fullscreen_container.setStyleSheet("background-color: black;")
            
            # Create layout for fullscreen
            fs_layout = QVBoxLayout(self.fullscreen_container)
            fs_layout.setContentsMargins(0, 0, 0, 0)
            fs_layout.setSpacing(0)
            
            # Configure video widget for fullscreen
            self.video_widget.setParent(self.fullscreen_container)
            self.video_widget.setMinimumSize(QSize(0, 0))
            self.video_widget.setMaximumSize(QSize(16777215, 16777215))
            self.video_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
            self.video_widget.setStyleSheet("background-color: black;")
            
            # Add video widget to layout with stretch
            fs_layout.addWidget(self.video_widget, 1)

            # Configure subtitle label for fullscreen
            if hasattr(self, 'subtitle_label'):
                self.subtitle_label.setParent(self.fullscreen_container)
                self.subtitle_label.setAlignment(Qt.AlignCenter | Qt.AlignBottom)
                self.subtitle_label.raise_()
                self.subtitle_label.setStyleSheet("""
                    QLabel {
                        background-color: rgba(0, 0, 0, 0.5);
                        color: white;
                        padding: 15px;
                        font-size: 24px;
                        font-weight: bold;
                        margin: 40px;
                        border-radius: 10px;
                    }
                """)
                fs_layout.addWidget(self.subtitle_label, 0, Qt.AlignBottom)

            # Create controls container
            controls_container = QWidget(self.fullscreen_container)
            controls_container.setObjectName("fullscreen_controls")
            controls_container.setStyleSheet("""
                QWidget#fullscreen_controls {
                    background-color: rgba(0, 0, 0, 0.7);
                    border-top: 1px solid rgba(255, 255, 255, 0.1);
                }
            """)
            controls_container.setFixedHeight(60)

            # Create controls layout
            self.fs_controls_layout = QHBoxLayout(controls_container) # Store as instance member
            self.fs_controls_layout.setContentsMargins(15, 8, 15, 8)
            self.fs_controls_layout.setSpacing(10)

            # Create control buttons with consistent styling
            button_style = """
                QToolButton {
                    background-color: transparent;
                    border: none;
                    border-radius: 4px;
                    padding: 4px;
                }
                QToolButton:hover {
                    background-color: rgba(255, 255, 255, 0.1);
                }
                QToolButton:pressed {
                    background-color: rgba(255, 255, 255, 0.2);
                }
            """

            # Create and configure fullscreen controls
            fs_play_button = QToolButton()
            fs_play_button.setIcon(self.play_button.icon())
            fs_play_button.setIconSize(QSize(24, 24))
            fs_play_button.setStyleSheet(button_style)
            fs_play_button.clicked.connect(self.toggle_play)

            fs_position_slider = QSlider(Qt.Horizontal)
            fs_position_slider.setRange(0, self.position_slider.maximum())
            fs_position_slider.setValue(self.position_slider.value())
            fs_position_slider.setStyleSheet("""
                QSlider::groove:horizontal {
                    border: none;
                    height: 4px;
                    background: rgba(255, 255, 255, 0.3);
                    margin: 0px;
                }
                QSlider::handle:horizontal {
                    background: white;
                    border: none;
                    width: 12px;
                    height: 12px;
                    margin: -4px 0;
                    border-radius: 6px;
                }
                QSlider::sub-page:horizontal {
                    background: #2196F3;
                }
            """)
            fs_position_slider.sliderMoved.connect(self.set_position_from_slider)
            fs_position_slider.sliderPressed.connect(self.player.pause)
            fs_position_slider.sliderReleased.connect(self.player.play)

            fs_time_label = QLabel(self.time_label.text())
            fs_time_label.setStyleSheet("color: white; font-size: 12px;")
            fs_time_label.setFixedWidth(100)

            fs_mute_button = QToolButton()
            fs_mute_button.setIcon(self.mute_button.icon())
            fs_mute_button.setIconSize(QSize(24, 24))
            fs_mute_button.setStyleSheet(button_style)
            fs_mute_button.clicked.connect(self.toggle_mute)

            fs_volume_slider = QSlider(Qt.Horizontal)
            fs_volume_slider.setRange(0, 100)
            fs_volume_slider.setValue(self.volume_slider.value())
            fs_volume_slider.setStyleSheet(fs_position_slider.styleSheet())
            fs_volume_slider.setMaximumWidth(100)
            fs_volume_slider.valueChanged.connect(self.set_volume)

            fs_fullscreen_button = QToolButton()
            fs_fullscreen_button.setIcon(self.get_icon("fullscreen-exit.png", "view-restore"))
            fs_fullscreen_button.setIconSize(QSize(24, 24))
            fs_fullscreen_button.setStyleSheet(button_style)
            fs_fullscreen_button.clicked.connect(self.toggle_fullscreen)

            # Add controls to layout
            self.fs_controls_layout.addWidget(fs_play_button)
            self.fs_controls_layout.addWidget(fs_position_slider)
            self.fs_controls_layout.addWidget(fs_time_label)
            self.fs_controls_layout.addSpacing(10)
            self.fs_controls_layout.addWidget(fs_mute_button)
            self.fs_controls_layout.addWidget(fs_volume_slider)
            self.fs_controls_layout.addSpacing(10)
            self.fs_controls_layout.addWidget(fs_fullscreen_button)

            # Define LTR order for fullscreen control items
            self.fullscreen_control_items_ltr = [
                (fs_play_button, 'widget'),
                (fs_position_slider, 'widget'),
                (fs_time_label, 'widget'),
                (10, 'spacing'),
                (fs_mute_button, 'widget'),
                (fs_volume_slider, 'widget'),
                (10, 'spacing'),
                (fs_fullscreen_button, 'widget'),
            ]

            # Build the fullscreen controls layout using the defined order and current direction
            app_instance = QApplication.instance()
            current_direction = app_instance.layoutDirection() if app_instance else Qt.LeftToRight
            self._rebuild_controls_layout(self.fs_controls_layout, self.fullscreen_control_items_ltr, current_direction)
            
            # Store references to fullscreen controls for direct access (e.g., updating icons)
            self.fs_controls = {
                'play_button': fs_play_button,
                'position_slider': fs_position_slider,
                'time_label': fs_time_label,
                'mute_button': fs_mute_button,
                'volume_slider': fs_volume_slider,
                'fullscreen_button': fs_fullscreen_button
            }

            # Add controls to main layout
            fs_layout.addWidget(controls_container)

            # Show fullscreen
            self.fullscreen_container.showFullScreen()
            self.fullscreen_container.installEventFilter(self)
            self.is_fullscreen = True
            
            # Ensure the video widget has focus for keyboard events
            self.video_widget.setFocus()
            
            # Re-embed VLC with proper scaling
            QTimer.singleShot(100, self._embed_vlc)
            
        else:
            # Exit fullscreen mode
            if hasattr(self, 'fullscreen_container'):
                # Reset video widget properties
                self.video_widget.setParent(self)
                self.video_widget.setMinimumSize(320, 180)
                self.video_widget.setMaximumSize(16777215, 16777215)
                self.layout().insertWidget(0, self.video_widget)
                
                # Restore subtitle label
                if hasattr(self, 'subtitle_label'):
                    self.subtitle_label.setParent(self)
                    self.layout().insertWidget(1, self.subtitle_label)
                    self.subtitle_label.setStyleSheet("""
                        QLabel {
                            background-color: rgba(0, 0, 0, 0.7);
                            color: white;
                            padding: 10px;
                            font-size: 16px;
                            font-weight: bold;
                            border-radius: 5px;
                        }
                    """)
                
                # Clean up fullscreen controls
                if hasattr(self, 'fs_controls'):
                    del self.fs_controls
                
                # Close and cleanup fullscreen container
                self.fullscreen_container.close()
                self.fullscreen_container.deleteLater()
            
            if self.normal_geometry:
                self.parent().setGeometry(self.normal_geometry)
            
            self.is_fullscreen = False
            self.fullscreen_button.setIcon(self.get_icon("fullscreen.png", "view-fullscreen"))
            
            # Ensure the video widget has focus
            self.video_widget.setFocus()
            
            # Re-embed VLC with normal scaling
            QTimer.singleShot(100, self._embed_vlc)

# --- MainWindow Class (Updated Section) ---
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.subtitle_data = None
        self.translated_data = None
        self.video_path = None
        self.current_srt_for_vlc = None
        self.current_language = "English"  # Langue par défaut
        self.icons_dir = os.path.join(getattr(sys, '_MEIPASS', os.path.dirname(os.path.abspath(__file__))), "icons")
        os.makedirs(self.icons_dir, exist_ok=True)
        self.init_ui()
        self.create_actions_and_menus()
        self.init_status_bar()
        self.create_shortcuts()

    def change_language(self, language):
        """Change l'interface dans la langue sélectionnée"""
        self.current_language = language

        q_app = QApplication.instance()
        if q_app:  # Ensure QApplication instance exists
            if language == "العربية":
                q_app.setLayoutDirection(Qt.RightToLeft)
            else:
                q_app.setLayoutDirection(Qt.LeftToRight)
        
        # Update video player controls layout
        if hasattr(self, 'video_player') and self.video_player:
            self.video_player.set_layout_direction_for_controls(q_app.layoutDirection() if q_app else Qt.LeftToRight)

        # Mise à jour des textes des boutons
        self.upload_button.setText(TRANSLATIONS[language]["upload_video"])
        self.generate_button.setText(TRANSLATIONS[language]["generate_subtitles"])
        self.summarize_button.setText(TRANSLATIONS[language]["summarize_video"])
        self.translate_button.setText(TRANSLATIONS[language]["translate_subtitles"])
        self.export_button.setText(TRANSLATIONS[language]["export_current"])
        
        # Mise à jour des labels
        self.model_label.setText(TRANSLATIONS[language]["model_label"])
        self.source_lang_label.setText(TRANSLATIONS[language]["source_language"])
        self.translate_to_label.setText(TRANSLATIONS[language]["translate_to"])  # Changed from language_label
        self.app_language_label.setText(TRANSLATIONS[language]["app_language"])
        
        # Mise à jour des onglets
        self.subtitle_tabs.setTabText(0, TRANSLATIONS[language]["original_subtitles"])
        self.subtitle_tabs.setTabText(1, TRANSLATIONS[language]["translated_subtitles"])
        self.subtitle_tabs.setTabText(2, TRANSLATIONS[language]["video_summary"])

    def init_ui(self):
        # Set window icon first with larger size
        icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "app_icon.png")
        if os.path.exists(icon_path):
            icon = QIcon(icon_path)
            # Create a larger icon
            self.setWindowIcon(icon)
            # Set larger icon size for title bar
            self.setIconSize(QSize(48, 48))  # Increased size to 48x48

        self.setWindowTitle(f"{APP_NAME} - v{APP_VERSION}")
        self.setGeometry(100, 100, 1350, 850) # Slightly wider for comfort

        central_widget = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setContentsMargins(10,10,10,10)
        main_layout.setSpacing(8)

        splitter = QSplitter(Qt.Horizontal)
        splitter.setHandleWidth(3)

        self.video_player_container = QWidget()
        video_layout = QVBoxLayout()
        video_layout.setContentsMargins(0,0,0,0)
        self.video_player = VideoPlayer(self)
        self.video_player.error_occurred.connect(self.show_status_message)
        video_layout.addWidget(self.video_player)
        self.video_player_container.setLayout(video_layout)
        splitter.addWidget(self.video_player_container)

        right_panel_widget = QWidget()
        right_panel_layout = QVBoxLayout()
        right_panel_layout.setContentsMargins(8,8,8,8)
        right_panel_layout.setSpacing(10)

        generation_controls_layout = QGridLayout()
        generation_controls_layout.setSpacing(10)

        # Ajout du sélecteur de langue de l'application
        app_language_layout = QHBoxLayout()
        self.app_language_label = QLabel(TRANSLATIONS[self.current_language]["app_language"])
        self.app_language_combo = QComboBox()
        self.app_language_combo.addItems(list(TRANSLATIONS.keys()))
        self.app_language_combo.setCurrentText(self.current_language)
        self.app_language_combo.currentTextChanged.connect(self.change_language)
        app_language_layout.addWidget(self.app_language_label)
        app_language_layout.addWidget(self.app_language_combo)
        generation_controls_layout.addLayout(app_language_layout, 0, 0, 1, 2)

        self.upload_button = QPushButton(self.video_player.get_icon("upload.png", "document-open"), TRANSLATIONS[self.current_language]["upload_video"])
        self.upload_button.setStyleSheet(self.get_primary_button_style())
        self.upload_button.clicked.connect(self.upload_video)
        generation_controls_layout.addWidget(self.upload_button, 1, 0, 1, 2)

        self.model_label = QLabel(TRANSLATIONS[self.current_language]["model_label"])
        generation_controls_layout.addWidget(self.model_label, 2, 0)
        self.model_combo = QComboBox()
        self.model_combo.addItems(WHISPER_MODELS)
        self.model_combo.setCurrentText(DEFAULT_WHISPER_MODEL)
        self.model_combo.setToolTip("Select Whisper model (smaller is faster, larger is more accurate)")
        generation_controls_layout.addWidget(self.model_combo, 2, 1)

        self.source_lang_label = QLabel(TRANSLATIONS[self.current_language]["source_language"])
        generation_controls_layout.addWidget(self.source_lang_label, 3, 0)
        self.source_lang_combo = QComboBox()
        self.whisper_languages = {"Auto": "auto", "English": "en", "French": "fr", "Spanish": "es", "German": "de", "Arabic": "ar"}
        self.source_lang_combo.addItems(self.whisper_languages.keys())
        self.source_lang_combo.setCurrentText("Auto")
        self.source_lang_combo.setToolTip("Specify source language for Whisper (optional, 'auto' for detection)")
        generation_controls_layout.addWidget(self.source_lang_combo, 3, 1)

        self.generate_button = QPushButton(self.video_player.get_icon("generate.png", "process-start"), TRANSLATIONS[self.current_language]["generate_subtitles"])
        self.generate_button.setStyleSheet(self.get_primary_button_style())
        self.generate_button.clicked.connect(self.generate_subtitles)
        self.generate_button.setEnabled(False)
        generation_controls_layout.addWidget(self.generate_button, 4, 0, 1, 2)

        self.summarize_button = QPushButton(self.video_player.get_icon("summarize.png", "text-enriched"), TRANSLATIONS[self.current_language]["summarize_video"])
        self.summarize_button.setStyleSheet(self.get_button_style())
        self.summarize_button.clicked.connect(self.summarize_video_content)
        self.summarize_button.setEnabled(False)
        generation_controls_layout.addWidget(self.summarize_button, 5, 0, 1, 2)

        self.translate_to_label = QLabel(TRANSLATIONS[self.current_language]["translate_to"])
        generation_controls_layout.addWidget(self.translate_to_label, 6, 0)
        self.language_combo = QComboBox()
        self.target_languages = {
            "Arabic": "ar",
            "Bengali": "bn",
            "Bulgarian": "bg",
            "Chinese (Simplified)": "zh-CN",
            "Chinese (Traditional)": "zh-TW",
            "Croatian": "hr",
            "Danish": "da",
            "Dutch": "nl",
            "English": "en",
            "Filipino": "tl",
            "French": "fr",
            "German": "de",
            "Greek": "el",
            "Hindi": "hi",
            "Hungarian": "hu",
            "Indonesian": "id",
            "Italian": "it",
            "Japanese": "ja",
            "Korean": "ko",
            "Malay": "ms",
            "Norwegian": "no",
            "Polish": "pl",
            "Portuguese": "pt",
            "Romanian": "ro",
            "Russian": "ru",
            "Serbian": "sr",
            "Slovak": "sk",
            "Spanish": "es",
            "Swedish": "sv",
            "Thai": "th",
            "Turkish": "tr",
            "Ukrainian": "uk",
            "Vietnamese": "vi"
        }
        self.language_combo.addItems(self.target_languages.keys())
        try: self.language_combo.setCurrentText("French") # Changé pour French comme défaut
        except: self.language_combo.setCurrentIndex(0)
        generation_controls_layout.addWidget(self.language_combo, 6, 1)

        self.translate_button = QPushButton(self.video_player.get_icon("translate.png", "format-text-direction-ltr"), TRANSLATIONS[self.current_language]["translate_subtitles"])
        self.translate_button.setStyleSheet(self.get_button_style())
        self.translate_button.clicked.connect(self.translate_subtitles)
        self.translate_button.setEnabled(False)
        generation_controls_layout.addWidget(self.translate_button, 7, 0, 1, 2)

        self.export_button = QPushButton(self.video_player.get_icon("export.png", "document-save"), TRANSLATIONS[self.current_language]["export_current"])
        self.export_button.setStyleSheet(self.get_button_style())
        self.export_button.clicked.connect(self.export_content)
        self.export_button.setEnabled(False)
        generation_controls_layout.addWidget(self.export_button, 8, 0, 1, 2)

        right_panel_layout.addLayout(generation_controls_layout)
        right_panel_layout.addStretch(1)

        self.subtitle_tabs = QTabWidget()
        self.original_subtitle_widget = QTextEdit()
        self.original_subtitle_widget.setReadOnly(True)
        self.original_subtitle_widget.setFont(QFont("Consolas", 10))
        self.original_subtitle_widget.setStyleSheet("QTextEdit { line-height: 1.6; background-color: #2E2E2E; color: #F0F0F0; border: 1px solid #444; padding: 5px; }")

        self.translated_subtitle_widget = QTextEdit()
        self.translated_subtitle_widget.setReadOnly(True)
        self.translated_subtitle_widget.setFont(QFont("Consolas", 10))
        self.translated_subtitle_widget.setStyleSheet("QTextEdit { line-height: 1.6; background-color: #2E2E2E; color: #F0F0F0; border: 1px solid #444; padding: 5px; }")

        self.summary_widget = QTextEdit()
        self.summary_widget.setReadOnly(True)
        self.summary_widget.setFont(QFont("Arial", 11))
        self.summary_widget.setStyleSheet("QTextEdit { line-height: 1.5; background-color: #2E2E2E; color: #F0F0F0; border: 1px solid #444; padding: 8px; }")

        self.subtitle_tabs.addTab(self.original_subtitle_widget, TRANSLATIONS[self.current_language]["original_subtitles"])
        self.subtitle_tabs.addTab(self.translated_subtitle_widget, TRANSLATIONS[self.current_language]["translated_subtitles"])
        self.subtitle_tabs.addTab(self.summary_widget, TRANSLATIONS[self.current_language]["video_summary"])
        
        tab_policy = self.subtitle_tabs.sizePolicy()
        tab_policy.setVerticalStretch(1)
        self.subtitle_tabs.setSizePolicy(tab_policy)
        right_panel_layout.addWidget(self.subtitle_tabs, stretch=5)

        right_panel_widget.setLayout(right_panel_layout)
        splitter.addWidget(right_panel_widget)
        splitter.setSizes([int(self.width() * 0.55), int(self.width() * 0.45)]) # Adjust splitter ratio

        main_layout.addWidget(splitter)

        self.progress_bar = QProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.progress_bar.setTextVisible(True)
        self.progress_bar.setFormat("Idle")
        self.progress_bar.setAlignment(Qt.AlignCenter)
        self.progress_bar.setFixedHeight(20)
        main_layout.addWidget(self.progress_bar)

        central_widget.setLayout(main_layout)
        self.setCentralWidget(central_widget)

    def get_button_style(self):
        return """QPushButton { ... }""" # Keep your existing style
    def get_primary_button_style(self):
        return """QPushButton { ... }""" # Keep your existing style

    def create_actions_and_menus(self): # Keep as is
        exit_action = QAction(self.video_player.get_icon("exit.png", "application-exit"), "&Exit", self)
        exit_action.setShortcut("Ctrl+Q")
        exit_action.setStatusTip("Exit application")
        exit_action.triggered.connect(self.close)
        about_action = QAction(self.video_player.get_icon("about.png", "help-about"), "&About", self)
        about_action.setStatusTip("Show About dialog")
        about_action.triggered.connect(self.show_about_dialog)
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")
        file_menu.addAction(exit_action)
        help_menu = menu_bar.addMenu("&Help")
        help_menu.addAction(about_action)

    def init_status_bar(self): # Keep as is
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.status_bar.showMessage("Ready. Upload a video to start.", 7000)

    def show_status_message(self, message, timeout=7000): # Keep as is
        self.status_bar.showMessage(message, timeout)

    def update_progress(self, value, text=""): # MODIFIED: Accept text for progress bar
        self.progress_bar.setValue(value)
        if text:
            self.progress_bar.setFormat(f"{text} %p%")
        elif value == 0:
            self.progress_bar.setFormat("Idle")
        elif value == 100:
             self.progress_bar.setFormat("Complete! %p%")
        else: # Default if no text provided but in progress
            self.progress_bar.setFormat("Processing... %p%")


    # --- Methods like upload_video, generate_subtitles, on_transcription_complete, etc. ---
    # These will need to call self.update_progress with the new signature (value, text)
    # For example, in generate_subtitles before worker.start():
    # self.update_progress(0, "Starting subtitle generation...")

    # And connect worker signals:
    # self.subtitle_worker.progress_updated.connect(self.update_progress) # This connects to the new slot

    # ... (Rest of MainWindow methods, ensure they connect to and call the new update_progress)
    # ... (export_content, show_error, format_timestamp (can be removed if VideoPlayer's is used), show_about_dialog, cleanup_temp_srt, closeEvent)
    # ... (Ensure all methods from your previous complete code are here)
    
    # Make sure the worker finished signals also update the progress bar to a final state.
    # e.g., self.subtitle_worker.finished.connect(lambda: self.update_progress(100 if self.subtitle_data else 0, "Transcription Finished"))

    def upload_video(self):
        self.cleanup_temp_srt()
        file_path, _ = QFileDialog.getOpenFileName(self, "Select Video File", str(Path.home()), "Video Files (*.mp4 *.avi *.mkv *.mov *.webm *.flv);;All Files (*)")
        if file_path:
            if self.video_path and self.video_player: self.video_player.stop_player()
            self.video_path = file_path
            self.video_player.set_video(file_path)
            self.subtitle_data = None
            self.translated_data = None
            self.original_subtitle_widget.clear()
            self.translated_subtitle_widget.clear()
            self.summary_widget.clear()
            self.update_progress(0, "Idle") # Reset progress bar
            self.generate_button.setEnabled(True)
            self.translate_button.setEnabled(False)
            self.summarize_button.setEnabled(False)
            self.export_button.setEnabled(False)
            self.show_status_message(f"Loaded: {os.path.basename(file_path)}")
            self.setWindowTitle(f"{APP_NAME} - {os.path.basename(file_path)}")

    def generate_subtitles(self):
        if not self.video_path: self.show_error("Please upload a video file first."); return
        self.generate_button.setEnabled(False); self.translate_button.setEnabled(False); self.summarize_button.setEnabled(False); self.export_button.setEnabled(False)
        self.update_progress(0, "Preparing transcription...")
        self.original_subtitle_widget.clear(); self.translated_subtitle_widget.clear(); self.summary_widget.clear()
        self.subtitle_data = None; self.translated_data = None
        selected_model = self.model_combo.currentText()
        source_lang_code = self.whisper_languages.get(self.source_lang_combo.currentText())
        self.subtitle_worker = SubtitleWorker(self.video_path, selected_model, source_lang_code)
        self.subtitle_worker.progress_updated.connect(self.update_progress)
        self.subtitle_worker.transcription_complete.connect(self.on_transcription_complete)
        self.subtitle_worker.error_occurred.connect(self.show_status_message)
        self.subtitle_worker.finished.connect(lambda: (self.generate_button.setEnabled(True), self.update_progress(self.progress_bar.value(), "Transcription process finished." if self.progress_bar.value() < 100 else "Transcription Complete!")))
        self.show_status_message(f"Generating subtitles with '{selected_model}' for '{os.path.basename(self.video_path)}'...")
        self.subtitle_worker.start()

    def on_transcription_complete(self, result):
        self.subtitle_data = result
        if result and result.get("segments"):
            self.video_player.set_subtitles_for_overlay(result.get("segments", []))
            for segment in result["segments"]:
                start_time = self.video_player.format_srt_timestamp(segment.get("start",0))
                end_time = self.video_player.format_srt_timestamp(segment.get("end",0))
                self.original_subtitle_widget.append(f"<i>{start_time} --> {end_time}</i><br/>{segment.get('text','')}<br/>")
            self.translate_button.setEnabled(True)
            self.export_button.setEnabled(True)
            if result.get("text","").strip():
                self.summarize_button.setEnabled(True)
            self.update_progress(100, "Transcription Complete!")
            self.play_notification_sound("transcription")
        else:
            self.original_subtitle_widget.setText("No segments found or error in transcription.")
            self.update_progress(0,"Transcription failed to produce segments.")
        detected_lang = result.get('language', 'N/A') if result else 'N/A'
        self.show_status_message(f"Transcription complete! Detected Language: {detected_lang}")

    def summarize_video_content(self):
        if not self.subtitle_data or not self.subtitle_data.get("text", "").strip(): self.show_error("Generate subtitles first for summarization."); return
        original_text = self.subtitle_data.get("text")
        gemini_api_key = os.getenv("GEMINI_API_KEY")
        self.summarize_button.setEnabled(False); self.update_progress(0, "Preparing summarization...")
        self.summary_widget.clear()
        self.summarization_worker = GeminiSummarizationWorker(original_text, gemini_api_key)
        self.summarization_worker.progress_updated.connect(self.update_progress)
        self.summarization_worker.summarization_complete.connect(self.on_summarization_complete)
        self.summarization_worker.error_occurred.connect(self.show_status_message)
        self.summarization_worker.finished.connect(lambda: (self.summarize_button.setEnabled(True), self.update_progress(self.progress_bar.value(), "Summarization Finished.")))
        self.show_status_message(f"Summarizing content...")
        self.summarization_worker.start()

    def on_summarization_complete(self, summary_text):
        self.summary_widget.setText(summary_text if summary_text else "No summary generated or error occurred.")
        self.subtitle_tabs.setCurrentWidget(self.summary_widget)
        self.update_progress(100, "Summarization Complete!")
        self.export_button.setEnabled(True)
        self.play_notification_sound("summary")

    def translate_subtitles(self):
        if not self.subtitle_data or not self.subtitle_data.get("segments"): self.show_error("Generate subtitles with segments first."); return
        target_lang_code = self.target_languages.get(self.language_combo.currentText())
        if not target_lang_code: self.show_error(f"Invalid target language."); return
        self.translate_button.setEnabled(False); self.update_progress(0, "Preparing translation...");
        self.translated_subtitle_widget.clear(); self.translated_data = None
        self.translation_worker = TranslationWorker(self.subtitle_data, target_lang_code)
        self.translation_worker.progress_updated.connect(self.update_progress)
        self.translation_worker.translation_complete.connect(self.on_translation_complete)
        self.translation_worker.error_occurred.connect(self.show_status_message)
        self.translation_worker.finished.connect(lambda: (self.translate_button.setEnabled(True), self.update_progress(self.progress_bar.value(), "Translation Finished.")))
        self.show_status_message(f"Translating subtitles to {self.language_combo.currentText()}...")
        self.translation_worker.start()

    def on_translation_complete(self, result):
        self.translated_data = result
        if result and result.get("segments"):
            for segment in result["segments"]:
                start_time = self.video_player.format_srt_timestamp(segment.get("start",0))
                end_time = self.video_player.format_srt_timestamp(segment.get("end",0))
                self.translated_subtitle_widget.append(f"<i>{start_time} --> {end_time}</i><br/>{segment.get('text','')}<br/>")
            self.subtitle_tabs.setCurrentWidget(self.translated_subtitle_widget)
            self.export_button.setEnabled(True)
            self.update_progress(100, "Translation Complete!")
            self.play_notification_sound("translation")
            
            # Update subtitles in video player
            self.video_player.set_subtitles_for_overlay(result.get("segments", []))
            self.video_player.subtitle_label.show()
            if not self.video_player.subtitle_timer.isActive():
                self.video_player.subtitle_timer.start(100)
            
            # Load subtitles into VLC
            self.video_player.load_preferred_subtitles_to_vlc()
        else:
            self.translated_subtitle_widget.setText("No segments in translation or error occurred.")
            self.update_progress(0, "Translation failed to produce segments.")
        self.show_status_message(f"Translation to {self.language_combo.currentText()} complete!")

    def export_content(self):
        current_tab_widget = self.subtitle_tabs.currentWidget()
        export_data_dict = None; export_text = ""; default_filename = "export"; file_filter = "All Files (*)"; export_type_name = "Content"
        if current_tab_widget == self.summary_widget:
            export_text = self.summary_widget.toPlainText()
            if not export_text.strip(): self.show_error("No summary text to export."); return
            default_filename = f"{Path(self.video_path).stem}_summary.txt" if self.video_path else "summary.txt"; file_filter = "Text Files (*.txt);;All Files (*)"; export_type_name = "Summary"
        elif current_tab_widget == self.translated_subtitle_widget and self.translated_data:
            export_data_dict = self.translated_data; lang_code = self.translated_data.get("language", "translated")
            default_filename = f"{Path(self.video_path).stem}_subs_{lang_code}.srt" if self.video_path else f"subtitles_{lang_code}.srt"; file_filter = "SubRip Files (*.srt);;All Files (*)"; export_type_name = "Translated Subtitles"
        elif current_tab_widget == self.original_subtitle_widget and self.subtitle_data:
            export_data_dict = self.subtitle_data; lang_code = self.subtitle_data.get("language", "original")
            default_filename = f"{Path(self.video_path).stem}_subs_{lang_code}.srt" if self.video_path else f"subtitles_{lang_code}.srt"; file_filter = "SubRip Files (*.srt);;All Files (*)"; export_type_name = "Original Subtitles"
        else: self.show_error("No content available to export from the current tab."); return
        if export_data_dict and (not export_data_dict.get("segments")): self.show_error(f"No subtitle segments to export for {export_type_name}."); return
        initial_dir = os.path.dirname(self.video_path) if self.video_path else str(Path.home())
        file_path, _ = QFileDialog.getSaveFileName(self, f"Save {export_type_name}", os.path.join(initial_dir, default_filename), file_filter)
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8', errors='replace') as f:
                    if export_text: f.write(export_text)
                    elif export_data_dict:
                        for i, segment in enumerate(export_data_dict["segments"]):
                            f.write(f"{i + 1}\n"); start_time = self.video_player.format_srt_timestamp(segment.get("start",0)); end_time = self.video_player.format_srt_timestamp(segment.get("end",0))
                            f.write(f"{start_time} --> {end_time}\n"); f.write(f"{segment.get('text','')}\n\n")
                self.show_status_message(f"{export_type_name} exported to {os.path.basename(file_path)}")
            except Exception as e: self.show_error(f"Error exporting {export_type_name.lower()}: {str(e)}")

    def show_error(self, message):
        error_box = QMessageBox(self)
        error_box.setIcon(QMessageBox.Critical)
        error_box.setWindowTitle("Error")
        error_box.setText(message)
        error_box.setStandardButtons(QMessageBox.Ok)
        error_box.setStyleSheet("QMessageBox { background-color: #2d2d2d; color: #f0f0f0; font-size: 14px;} QMessageBox QLabel { color: #f0f0f0; } QPushButton { background-color: #2196F3; color: white; border: none; border-radius: 4px; padding: 6px 12px; min-width: 80px; } QPushButton:hover { background-color: #1E88E5; } QPushButton:pressed { background-color: #1976D2; }")
        error_box.exec_()
        self.show_status_message(f"Error: {message[:60]}...", 10000)

        # Enable/disable buttons based on state
        has_subtitles = bool(self.subtitle_data and self.subtitle_data.get("segments"))
        has_translation = bool(self.translated_data and self.translated_data.get("segments"))
        has_summary = bool(self.summary_widget.toPlainText().strip())

        self.generate_button.setEnabled(bool(self.video_path))
        self.translate_button.setEnabled(has_subtitles)
        self.summarize_button.setEnabled(has_subtitles)
        self.export_button.setEnabled(has_subtitles or has_translation or has_summary)

    def show_about_dialog(self):
        QMessageBox.about(self, f"About {APP_NAME}", f"Version: {APP_VERSION}\n\nA tool for generating, translating, and summarizing video subtitles using OpenAI Whisper, Google Translate, and Sumy.\n\nDeveloped with Python, PyQt5, and Python-VLC.")

    def cleanup_temp_srt(self):
        if self.current_srt_for_vlc and os.path.exists(self.current_srt_for_vlc):
            try: os.remove(self.current_srt_for_vlc); self.current_srt_for_vlc = None
            except OSError as e: print(f"Could not remove temp SRT file: {e}")

    def closeEvent(self, event):
        reply = QMessageBox.question(self, 'Confirm Exit', "Are you sure you want to exit?", QMessageBox.Yes | QMessageBox.No, QMessageBox.No)
        if reply == QMessageBox.Yes:
            if self.video_player: self.video_player.stop_player()
            self.cleanup_temp_srt(); event.accept()
        else: event.ignore()

    def play_notification_sound(self, task_type="default"):
        """Joue un son de notification différent selon le type de tâche terminée."""
        try:
            if task_type == "transcription":
                winsound.Beep(1000, 500)  # 1000Hz pendant 500ms
            elif task_type == "translation":
                winsound.Beep(800, 300)   # 800Hz pendant 300ms
            elif task_type == "summary":
                winsound.Beep(600, 200)   # 600Hz pendant 200ms
            else:
                winsound.Beep(440, 200)   # 440Hz pendant 200ms
        except:
            pass  # Ignorer les erreurs de son

    def create_shortcuts(self):
        """Create keyboard shortcuts for the application"""
        # Play/Pause shortcut
        self.play_shortcut = QAction(self)
        self.play_shortcut.setShortcut("Space")
        self.play_shortcut.triggered.connect(self.video_player.toggle_play)
        self.addAction(self.play_shortcut)

        # Mute/Unmute shortcut
        self.mute_shortcut = QAction(self)
        self.mute_shortcut.setShortcut("M")
        self.mute_shortcut.triggered.connect(self.video_player.toggle_mute)
        self.addAction(self.mute_shortcut)

        # Fullscreen shortcut
        self.fullscreen_shortcut = QAction(self)
        self.fullscreen_shortcut.setShortcut("F")
        self.fullscreen_shortcut.triggered.connect(self.video_player.toggle_fullscreen)
        self.addAction(self.fullscreen_shortcut)

        # ESC to exit fullscreen (handled in VideoPlayer's eventFilter)

    def download_video_with_subtitles(self):
        if not self.video_path:
            self.show_error("Please upload a video first.")
            return

        subtitle_data_to_use = None
        source_description = ""

        # Prefer translated subtitles if available
        if self.translated_data and self.translated_data.get("segments"):
            subtitle_data_to_use = self.translated_data
            source_description = "translated"
        # Fallback to original subtitles
        elif self.subtitle_data and self.subtitle_data.get("segments"):
            subtitle_data_to_use = self.subtitle_data
            source_description = "original"
        else:
            self.show_error("No subtitles available to embed. Please generate or translate subtitles first.")
            return

        if not subtitle_data_to_use or not subtitle_data_to_use.get("segments"):
            self.show_error("Selected subtitle data has no segments.")
            return

        video_basename = Path(self.video_path).stem
        default_filename = f"{video_basename}_with_{source_description}_subs.mp4"
        initial_dir = os.path.dirname(self.video_path) if self.video_path else str(Path.home())

        output_path, _ = QFileDialog.getSaveFileName(
            self,
            "Save Video with Subtitles",
            os.path.join(initial_dir, default_filename),
            "Video Files (*.mp4);;All Files (*)"
        )

        if output_path:
            self.download_video_button.setEnabled(False)
            self.update_progress(0, "Preparing video download...")

            self.video_download_worker = VideoDownloadWorker(
                self.video_path,
                subtitle_data_to_use,
                output_path
            )
            self.video_download_worker.progress_updated.connect(self.update_progress)
            self.video_download_worker.download_complete.connect(self.on_video_download_complete)
            self.video_download_worker.error_occurred.connect(self.on_video_download_error)
            self.video_download_worker.finished.connect(lambda: self.download_video_button.setEnabled(bool(self.video_path) and (bool(self.subtitle_data and self.subtitle_data.get("segments")) or bool(self.translated_data and self.translated_data.get("segments")))))
            self.show_status_message(f"Starting video download with {source_description} subtitles to {os.path.basename(output_path)}...")
            self.video_download_worker.start()

    def on_video_download_complete(self, success, output_filepath):
        if success:
            self.update_progress(100, "Video download complete!")
            self.show_status_message(f"Video successfully saved to {os.path.basename(output_filepath)}")
            self.play_notification_sound("default") # Or a specific sound for download
        else:
            # Error message would have been shown by on_video_download_error
            self.update_progress(0, "Video download failed.")
            self.show_status_message(f"Failed to save video.")
        has_subtitles = bool(self.subtitle_data and self.subtitle_data.get("segments"))
        has_translation = bool(self.translated_data and self.translated_data.get("segments"))
        self.download_video_button.setEnabled(bool(self.video_path) and (has_subtitles or has_translation))


    def on_video_download_error(self, error_message):
        self.show_error(f"Video Download Error: {error_message}")
        self.update_progress(0, "Video download error.")
        has_subtitles = bool(self.subtitle_data and self.subtitle_data.get("segments"))
        has_translation = bool(self.translated_data and self.translated_data.get("segments"))
        self.download_video_button.setEnabled(bool(self.video_path) and (has_subtitles or has_translation))

# --- Global Functions (apply_styles, fix_ssl, ensure_nltk_data, main) ---
# These should be taken from the previous complete code.
# ensure_nltk_data can be simplified now that SummarizationWorker handles more specific checks.
def apply_styles(app): # Keep your full apply_styles function
    app.setStyle(QStyleFactory.create("Fusion")) # ... rest of your styles ...
    # (Make sure this is the full styling function from your working code)
    dark_palette = QPalette()
    dark_palette.setColor(QPalette.Window, QColor(45, 45, 45))
    dark_palette.setColor(QPalette.WindowText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.Base, QColor(35, 35, 35))
    dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.Text, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
    dark_palette.setColor(QPalette.ButtonText, QColor(220, 220, 220))
    dark_palette.setColor(QPalette.BrightText, Qt.red)
    dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
    dark_palette.setColor(QPalette.HighlightedText, Qt.black)
    dark_palette.setColor(QPalette.ToolTipBase, QColor(40,40,40))
    dark_palette.setColor(QPalette.ToolTipText, QColor(220,220,220))
    disabled_text_color = QColor(127, 127, 127); disabled_button_color = QColor(80, 80, 80)
    dark_palette.setColor(QPalette.Disabled, QPalette.Text, disabled_text_color)
    dark_palette.setColor(QPalette.Disabled, QPalette.WindowText, disabled_text_color)
    dark_palette.setColor(QPalette.Disabled, QPalette.ButtonText, disabled_text_color)
    dark_palette.setColor(QPalette.Disabled, QPalette.Button, disabled_button_color)
    dark_palette.setColor(QPalette.Disabled, QPalette.Highlight, QColor(80, 80, 80))
    dark_palette.setColor(QPalette.Disabled, QPalette.HighlightedText, disabled_text_color)
    app.setPalette(dark_palette)
    app.setStyleSheet("""
        QToolTip { border: 1px solid #2A2A2A; background-color: #282828; color: #D0D0D0; padding: 5px; border-radius: 4px; opacity: 230; }
        QSplitter::handle { background-color: #3A3A3A; } QSplitter::handle:hover { background-color: #4A4A4A; } QSplitter::handle:pressed { background-color: #2196F3; }
        QProgressBar { border: 1px solid #3A3A3A; border-radius: 4px; text-align: center; background-color: #2D2D2D; color: #D0D0D0; font-weight: bold; }
        QProgressBar::chunk { background-color: #2196F3; margin: 1px; border-radius: 3px; }
        QTabWidget::pane { border: 1px solid #3A3A3A; background-color: #2D2D2D; border-top-left-radius: 0px; border-top-right-radius: 4px; border-bottom-left-radius: 4px; border-bottom-right-radius: 4px;}
        QTabBar::tab { background-color: #3E3E3E; color: #B0B0B0; padding: 10px 20px; border: 1px solid #3A3A3A; border-bottom: none; border-top-left-radius: 4px; border-top-right-radius: 4px; margin-right: 1px; min-width: 100px; }
        QTabBar::tab:selected { background-color: #2D2D2D; color: #FFFFFF; border-bottom: 1px solid #2D2D2D; }
        QTabBar::tab:!selected:hover { background-color: #4A4A4A; color: #D0D0D0; }
        QComboBox { border: 1px solid #3A3A3A; border-radius: 4px; padding: 5px 10px; background-color: #2D2D2D; color: #D0D0D0; selection-background-color: #2196F3; }
        QComboBox::drop-down { subcontrol-origin: padding; subcontrol-position: top right; width: 25px; border-left-width: 1px; border-left-color: #3A3A3A; border-left-style: solid; border-top-right-radius: 4px; border-bottom-right-radius: 4px; }
        QComboBox::down-arrow { width: 12px; height: 12px; }
        QComboBox QAbstractItemView { border: 1px solid #3A3A3A; background-color: #2D2D2D; color: #D0D0D0; selection-background-color: #2196F3; selection-color: black; padding: 5px; }
        QSpinBox { border: 1px solid #3A3A3A; border-radius: 4px; padding: 5px 8px; background-color: #2D2D2D; color: #D0D0D0; min-width: 60px; selection-background-color: #2196F3; selection-color: black; }
        QSpinBox::up-button, QSpinBox::down-button { subcontrol-origin: border; width: 20px; border-left-width: 1px; border-left-color: #3A3A3A; border-left-style: solid; background-color: #3E3E3E; }
        QSpinBox::up-button:hover, QSpinBox::down-button:hover { background-color: #4A4A4A; }
        QSpinBox::up-button { subcontrol-position: top right; border-top-right-radius: 4px; } QSpinBox::down-button { subcontrol-position: bottom right; border-bottom-right-radius: 4px; }
        QSpinBox::up-arrow, QSpinBox::down-arrow { width: 10px; height: 10px; }
        QStatusBar { font-size: 13px; color: #B0B0B0; }
        QMenu { background-color: #2D2D2D; border: 1px solid #3A3A3A; padding: 5px; color: #D0D0D0;}
        QMenu::item { padding: 5px 20px 5px 20px; } QMenu::item:selected { background-color: #2196F3; color: black; }
        QMenuBar { background-color: #2D2D2D; color: #D0D0D0;}
        QMenuBar::item { background-color: #2D2D2D; padding: 5px 10px; } QMenuBar::item:selected { background-color: #3E3E3E; }
    """)


def fix_ssl():
    if hasattr(ssl, '_create_unverified_context'):
        try: ssl._create_default_https_context = ssl._create_unverified_context
        except Exception as e: print(f"Could not set unverified SSL context: {e}")

def ensure_nltk_data_basic(): # Simplified global check
    """Basic check for punkt, worker threads will do more specific language checks if needed."""
    try:
        nltk.data.find('tokenizers/punkt') # Remove quiet=True from here
        # print("Global NLTK 'punkt' data found.") # Optional: uncomment for confirmation
    except LookupError:
        print("Global NLTK 'punkt' data not found. Attempting basic download...")
        try:
            nltk.download('punkt', quiet=True) # quiet=True is fine for nltk.download
            print("Basic 'punkt' data downloaded successfully.")
        except Exception as e:
            print(f"Failed to download basic 'punkt' data: {e}.")
            print("If summarization fails, please try running this in a Python console:")
            print("import nltk")
            print("nltk.download('punkt')")
            print("nltk.download('stopwords')") # Also good to have stopwords globally
    except Exception as e_find: # Catch other potential errors from nltk.data.find
        print(f"An error occurred while checking for NLTK 'punkt' data: {e_find}")

def main():
    load_dotenv()
    # fix_ssl() # Uncomment if SSL errors occur (e.g., model downloads)
    for lib_name in ['nltk', 'whisper', 'vlc', 'deep_translator', 'PyQt5', 'google.generativeai', 'dotenv']:
        try: __import__(lib_name)
        except ImportError:
            QMessageBox.critical(None, "Dependency Error", f"The '{lib_name}' library is not installed. Please install it (e.g., pip install {lib_name} or pip install -r requirements.txt)", QMessageBox.Ok); sys.exit(1)
    
    ensure_nltk_data_basic()

    QApplication.setAttribute(Qt.AA_EnableHighDpiScaling, True)
    QApplication.setAttribute(Qt.AA_UseHighDpiPixmaps, True)
    app = QApplication(sys.argv)
    apply_styles(app)
    app.setApplicationName(APP_NAME); app.setApplicationVersion(APP_VERSION)
    
    # Modified icon loading code
    icon_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons", "app_icon.png")
    if os.path.exists(icon_path):
        app_icon = QIcon(icon_path)
        app.setWindowIcon(app_icon)
        # Also set the icon for the main window
        window = MainWindow()
        window.setWindowIcon(app_icon)
    else:
        print(f"Warning: Icon not found at {icon_path}")
        window = MainWindow()
    
    window.show()
    sys.exit(app.exec_())

if __name__ == '__main__':
    main()
