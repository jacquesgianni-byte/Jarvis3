"""
Jarvis Server Entry Point

Mirrors apps/desktop/main.py exactly:
    1. Load .env
    2. Initialise AI provider (same as Desktop)
    3. Create one Agent
    4. Hand it to the Flask app

The server is intentionally interface-agnostic. It is not an
"Android server" -- it is the Jarvis API. Desktop, Android, Web,
and CLI all connect to the same brain through this entry point.
"""

import logging
import os

from dotenv import load_dotenv

logger = logging.getLogger(__name__)


def main():
    # Step 1 -- Load environment (identical to desktop/main.py).
    load_dotenv()

    # Step 2 -- Initialise AI provider using the same path as Desktop.
    from core.ai.manager import AIManager
    from core.ai.providers.openai_provider import OpenAIProvider
    from core.ai.providers.anthropic_provider import AnthropicProvider
    from core.settings.settings import Settings
    _settings = Settings()
    ai = AIManager()
    ai.register_provider("openai", OpenAIProvider())
    ai.register_provider("anthropic", AnthropicProvider())
    if not ai.activate(_settings.default_ai_provider):
        ai.activate("openai")

    # Step 3 -- Create one Agent (the single Jarvis brain).
    from core.agent import Agent
    agent = Agent(ai=ai)
    logger.info("[SERVER] Agent initialised.")

    # Step 3b -- Create system registries.
    from core.system.registry import SystemRegistry
    from core.system.session_registry import SessionRegistry
    system_registry  = SystemRegistry(agent=agent)
    session_registry = SessionRegistry()

    # Step 3c -- Create Engineering Coordinator for orchestrator approval workflow.
    # Genesis-053: persistent session store + approval gate
    from core.engineering.coordinator.coordinator import EngineeringCoordinator
    from core.engineering.coordinator.session_store import SessionStore
    session_store  = SessionStore()
    orchestrator   = EngineeringCoordinator(session_store=session_store)
    logger.info("[SERVER] EngineeringCoordinator initialised with SessionStore.")

    # Step 4 -- Create Flask app and inject the agent.
    from apps.server.app import create_app
    app = create_app(
        agent,
        system_registry=system_registry,
        session_registry=session_registry,
        orchestrator_coordinator=orchestrator,
    )

    # Configuration via environment with sensible defaults.
    host = os.getenv("JARVISS_SERVER_HOST", "0.0.0.0")
    port = int(os.getenv("JARVIS_SERVER_PORT", "5001"))
    debug = os.getenv("JARVIS_SERVER_DEBUG", "false").lower() == "true"

    logger.info("[SERVER] Starting Jarvis API on %s:%s", host, port)
    app.run(host=host, port=port, debug=debug)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
