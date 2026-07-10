"""
Jarvis Core

Main entry point for Jarvis.
"""

from core.settings import APP_NAME, VERSION
from core.logger import get_logger
from core.agent import Agent


def main():
    log = get_logger()

    print()
    print("=" * 50)
    print(f"        {APP_NAME} {VERSION}")
    print("=" * 50)

    log.info("Configuration loaded.")
    log.info("Logger initialized.")
    log.info("Event Bus initialized.")
    log.info("Jarvis Core started successfully.")

    print("✓ Configuration loaded")
    print("✓ Logger initialized")
    print("✓ Event Bus initialized")
    print()
    print("Good afternoon, Ludovic.")
    print("Jarvis Core is online and ready.")
    print("=" * 50)

    # Create Jarvis
    jarvis = Agent()

    # Conversation loop
    while True:

        request = input("\nYou: ").strip()

        if request.lower() in ("exit", "quit"):
            print("\nJarvis: Goodbye!")
            break

        if not request:
            continue

        response = jarvis.process(request)

        print(f"\nJarvis: {response}")


if __name__ == "__main__":
    main()