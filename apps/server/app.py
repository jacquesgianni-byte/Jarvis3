"""
Jarvis Flask Application Factory
Creates and configures the Flask app with one shared Agent instance.
This is the Jarvis API -- transport layer only. No business logic here.
Genesis-054 Sprint-001: mission_registry added.
Genesis-055 Sprint-001: mission_pipeline added.
"""
from __future__ import annotations
import logging
from flask import Flask

logger = logging.getLogger(__name__)

def create_app(
    agent,
    system_registry=None,
    session_registry=None,
    orchestrator_coordinator=None,
    mission_registry=None,
    mission_pipeline=None,
) -> Flask:
    app = Flask(__name__)
    app.config["AGENT"]                    = agent
    app.config["SYSTEM_REGISTRY"]          = system_registry
    app.config["SESSION_REGISTRY"]         = session_registry
    app.config["ORCHESTRATOR_COORDINATOR"] = orchestrator_coordinator
    app.config["MISSION_REGISTRY"]         = mission_registry
    app.config["MISSION_PIPELINE"]         = mission_pipeline
    from apps.server.routes import register_routes
    register_routes(app)
    from apps.server.orchestrator_routes import orchestrator_bp
    app.register_blueprint(orchestrator_bp)
    logger.info("[SERVER] Flask app created.")
    return app
