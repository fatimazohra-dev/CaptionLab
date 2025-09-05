from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QPushButton, QSlider, QLabel
from PyQt5.QtCore import Qt, pyqtSignal, QTimer
from PyQt5.QtGui import QIcon
import vlc
import sys

class VideoPlayer(QWidget):
    error_occurred = pyqtSignal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.instance = vlc.Instance()
        self.mediaplayer = self.instance.media_player_new()
        self.current_video_path = None
        self.subtitles_enabled = True
        self.init_ui()

    def init_ui(self):
        # Layout principal
        layout = QVBoxLayout()
        
        # Zone de lecture vidéo
        self.video_frame = QWidget()
        self.video_frame.setStyleSheet("background-color: black;")
        layout.addWidget(self.video_frame)
        
        # Contrôles
        controls_layout = QHBoxLayout()
        
        # Bouton play/pause
        self.play_button = QPushButton()
        self.play_button.setIcon(self.get_icon("play"))
        self.play_button.clicked.connect(self.toggle_play)
        controls_layout.addWidget(self.play_button)
        
        # Slider de position
        self.position_slider = QSlider(Qt.Horizontal)
        self.position_slider.setMaximum(1000)
        self.position_slider.sliderMoved.connect(self.set_position_from_slider)
        controls_layout.addWidget(self.position_slider)
        
        # Label de temps
        self.time_label = QLabel("00:00 / 00:00")
        controls_layout.addWidget(self.time_label)
        
        # Contrôle du volume
        self.volume_slider = QSlider(Qt.Horizontal)
        self.volume_slider.setMaximum(100)
        self.volume_slider.setValue(50)
        self.volume_slider.sliderMoved.connect(self.set_volume)
        controls_layout.addWidget(self.volume_slider)
        
        # Bouton mute
        self.mute_button = QPushButton()
        self.mute_button.setIcon(self.get_icon("volume"))
        self.mute_button.clicked.connect(self.toggle_mute)
        controls_layout.addWidget(self.mute_button)
        
        layout.addLayout(controls_layout)
        self.setLayout(layout)
        
        # Timer pour mettre à jour la position
        self.timer = QTimer()
        self.timer.setInterval(100)
        self.timer.timeout.connect(self.update_position_and_volume)

    def get_icon(self, icon_name, fallback_theme="application-default-icon"):
        return QIcon.fromTheme(icon_name, QIcon.fromTheme(fallback_theme))

    def set_video(self, video_path):
        self.current_video_path = video_path
        media = self.instance.media_new(video_path)
        self.mediaplayer.set_media(media)
        self._embed_vlc()
        self.timer.start()

    def _embed_vlc(self):
        if sys.platform.startswith('linux'):  # pour Linux
            self.mediaplayer.set_xwindow(self.video_frame.winId())
        elif sys.platform == "win32":  # pour Windows
            self.mediaplayer.set_hwnd(self.video_frame.winId())
        elif sys.platform == "darwin":  # pour MacOS
            self.mediaplayer.set_nsobject(int(self.video_frame.winId()))

    def toggle_play(self):
        if self.mediaplayer.is_playing():
            self.mediaplayer.pause()
            self.play_button.setIcon(self.get_icon("play"))
        else:
            self.mediaplayer.play()
            self.play_button.setIcon(self.get_icon("pause"))

    def update_position_and_volume(self):
        if not self.mediaplayer.is_playing():
            return

        # Mettre à jour la position
        length = self.mediaplayer.get_length()
        if length > 0:
            position = self.mediaplayer.get_position()
            self.position_slider.setValue(int(position * 1000))
            self.update_duration()

        # Mettre à jour le volume
        volume = self.mediaplayer.audio_get_volume()
        if volume >= 0:
            self.volume_slider.setValue(volume)
            self.update_mute_button_icon(volume)

    def update_duration(self):
        length = self.mediaplayer.get_length()
        time = self.mediaplayer.get_time()
        self.time_label.setText(f"{self.format_time(time)} / {self.format_time(length)}")

    def set_position_from_slider(self, value):
        self.mediaplayer.set_position(value / 1000.0)

    def set_volume(self, value):
        self.mediaplayer.audio_set_volume(value)

    def toggle_mute(self, force_mute=False, force_unmute=False):
        if force_mute:
            self.mediaplayer.audio_set_mute(True)
        elif force_unmute:
            self.mediaplayer.audio_set_mute(False)
        else:
            self.mediaplayer.audio_set_mute(not self.mediaplayer.audio_get_mute())
        self.update_mute_button_icon(self.mediaplayer.audio_get_volume())

    def update_mute_button_icon(self, volume):
        if self.mediaplayer.audio_get_mute() or volume == 0:
            self.mute_button.setIcon(self.get_icon("audio-volume-muted"))
        elif volume < 33:
            self.mute_button.setIcon(self.get_icon("audio-volume-low"))
        elif volume < 66:
            self.mute_button.setIcon(self.get_icon("audio-volume-medium"))
        else:
            self.mute_button.setIcon(self.get_icon("audio-volume-high"))

    def format_time(self, milliseconds):
        seconds = milliseconds // 1000
        minutes = seconds // 60
        seconds = seconds % 60
        return f"{minutes:02d}:{seconds:02d}"

    def set_subtitles_for_overlay(self, segments):
        self.subtitle_segments = segments
        self.update_subtitle_display()

    def update_subtitle_display(self):
        if not hasattr(self, 'subtitle_segments') or not self.subtitles_enabled:
            return

        current_time = self.mediaplayer.get_time() / 1000.0  # Convert to seconds
        current_subtitle = None

        for segment in self.subtitle_segments:
            if segment['start'] <= current_time <= segment['end']:
                current_subtitle = segment['text']
                break

        # Update subtitle display (implement your subtitle display logic here)
        if current_subtitle:
            # Update your subtitle label or overlay here
            pass

    def toggle_subtitles(self):
        self.subtitles_enabled = not self.subtitles_enabled
        self.update_subtitle_display()

    def stop_player(self):
        self.mediaplayer.stop()
        self.timer.stop()
        self.play_button.setIcon(self.get_icon("play")) 