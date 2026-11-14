import sys

from PySide6.QtWidgets import QApplication, QMainWindow


def run() -> int:
    app = QApplication(sys.argv)
    window = QMainWindow()
    window.setWindowTitle("DuckDesk")
    window.resize(1280, 800)
    window.show()
    return app.exec()
