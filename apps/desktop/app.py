"""
Desktop application launcher.
"""

import sys

from PySide6.QtWidgets import QApplication

from core.jarvis_core import JarvisCore
from apps.desktop.window import MainWindow


class DesktopApp:
    """
    Starts the Desktop application.
    """

    def __init__(self):
        self.app = QApplication(sys.argv)

        # Create the shared Jarvis Core.
        self.jarvis = JarvisCore()

        # Create the main window.
        self.window = MainWindow(self.jarvis)

    def run(self):
        self.window.show()
        return self.app.exec()