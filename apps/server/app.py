"""
Jarvis Flask Application Factory
Creates and configures the Flask app with one shared Agent instance.
This is the Jarvis API -- transport layer only. No business logic here.
Genesis-054 Sprint-001: mission_registry added.
Genesis-055 Sprint-001: mission_pipeline added.
Genesis-068 Sprint-003: genesis_contribution_store added.
"""
from __future__ import annotations
import pathlib
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
    # Genesis-064 Sprint-003c: sprint infrastructure
    from core.knowledge.sprint_state import SprintStateStore
    from core.knowledge.capability_gap import GapObservationStore
    _proj_root      = pathlib.Path(__file__).resolve().parents[2]
    _gap_data_dir   = _proj_root / "data" / "observations"
    _gap_data_dir.mkdir(parents=True, exist_ok=True)
    app.config["project_root"]       = _proj_root
    app.config["gap_store"]          = GapObservationStore(_gap_data_dir)
    app.config["sprint_state_store"] = SprintStateStore(_proj_root / "data")
    # Genesis-068 Sprint-003: Genesis-scope contribution log
    from core.knowledge.genesis_contributions import GenesisContributionStore
    app.config["genesis_contribution_store"] = GenesisContributionStore(_proj_root / "data")
    from apps.server.routes import register_routes
    register_routes(app)
    from apps.server.orchestrator_routes import orchestrator_bp
    app.register_blueprint(orchestrator_bp)
    from apps.server.sprint_routes import sprint_bp
    app.register_blueprint(sprint_bp)
    logger.info("[SERVER] Flask app created.")
    return app
