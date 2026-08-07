"""
Jarvis Flask Application Factory

Creates and configures the Flask app with one shared Agent instance.
This is the Jarvis API -- transport layer only. No business logic here.
"""

from __future__ import annotations

import logging
from flask import Flask

logger = logging.getLogger(__name__)


def create_app(agent, system_registry=None, session_registry=None) -> Flask:
    """
    Create the Flask application.

    Args:
        agent: A fully initialised Agent instance. The app never creates
               its own Agent -- it receives one via injection so the same
               brain can be shared across interfaces.

    Returns:
        Configured Flask application.
    """
    app = Flask(__name__)
    app.config["AGENT"]            = agent
    app.config["SYSTEM_REGISTRY"]  = system_registry
    app.config["SESSION_REGISTRY"] = session_registry

    # Register routes
    from apps.server.routes import register_routes
    register_routes(app)

    logger.info("[SERVER] Flask app created.")
    return app
