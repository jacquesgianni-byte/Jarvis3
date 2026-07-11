"""
Desktop launcher for Jarvis.
"""

from dotenv import load_dotenv

from apps.desktop.app import DesktopApp


def main():
    load_dotenv()

    app = DesktopApp()
    app.run()


if __name__ == "__main__":
    main()