"""
Desktop launcher for Jarvis.
"""

from apps.desktop.app import DesktopApp


def main():
    app = DesktopApp()
    app.run()


if __name__ == "__main__":
    main()