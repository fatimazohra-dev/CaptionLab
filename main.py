import sys
from PyQt5.QtWidgets import QApplication
from ui.main_window import MainWindow
from utils.styles import apply_styles
from utils.helpers import fix_ssl, ensure_nltk_data_basic

def main():
    # Fix SSL issues
    fix_ssl()
    
    # Ensure NLTK data is available
    ensure_nltk_data_basic()
    
    # Create application
    app = QApplication(sys.argv)
    
    # Apply styles
    apply_styles(app)
    
    # Create and show main window
    window = MainWindow()
    window.show()
    
    # Start event loop
    sys.exit(app.exec_())

if __name__ == '__main__':
    main() 