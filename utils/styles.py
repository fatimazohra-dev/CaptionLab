def apply_styles(app):
    app.setStyle("Fusion")
    
    # Style global
    style = """
    QMainWindow {
        background-color: #f0f0f0;
    }
    
    QPushButton {
        background-color: #2196F3;
        color: white;
        border: none;
        padding: 8px 16px;
        border-radius: 4px;
        min-width: 80px;
    }
    
    QPushButton:hover {
        background-color: #1976D2;
    }
    
    QPushButton:pressed {
        background-color: #0D47A1;
    }
    
    QPushButton:disabled {
        background-color: #BDBDBD;
    }
    
    QLineEdit, QTextEdit {
        padding: 8px;
        border: 1px solid #BDBDBD;
        border-radius: 4px;
        background-color: white;
    }
    
    QLineEdit:focus, QTextEdit:focus {
        border: 1px solid #2196F3;
    }
    
    QProgressBar {
        border: 1px solid #BDBDBD;
        border-radius: 4px;
        text-align: center;
        background-color: #E0E0E0;
    }
    
    QProgressBar::chunk {
        background-color: #2196F3;
        border-radius: 3px;
    }
    
    QSlider::groove:horizontal {
        border: 1px solid #BDBDBD;
        height: 8px;
        background: #E0E0E0;
        margin: 2px 0;
        border-radius: 4px;
    }
    
    QSlider::handle:horizontal {
        background: #2196F3;
        border: 1px solid #1976D2;
        width: 18px;
        margin: -2px 0;
        border-radius: 9px;
    }
    
    QSlider::handle:horizontal:hover {
        background: #1976D2;
    }
    
    QTabWidget::pane {
        border: 1px solid #BDBDBD;
        border-radius: 4px;
        background-color: white;
    }
    
    QTabBar::tab {
        background-color: #E0E0E0;
        border: 1px solid #BDBDBD;
        padding: 8px 16px;
        margin-right: 2px;
    }
    
    QTabBar::tab:selected {
        background-color: #2196F3;
        color: white;
    }
    
    QTabBar::tab:hover:!selected {
        background-color: #BDBDBD;
    }
    
    QStatusBar {
        background-color: #E0E0E0;
        color: #424242;
    }
    
    QMenuBar {
        background-color: #E0E0E0;
    }
    
    QMenuBar::item:selected {
        background-color: #2196F3;
        color: white;
    }
    
    QMenu {
        background-color: white;
        border: 1px solid #BDBDBD;
    }
    
    QMenu::item:selected {
        background-color: #2196F3;
        color: white;
    }
    """
    
    app.setStyleSheet(style) 