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
from pathlib import Path
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

    # Step 3c -- Create MissionRegistry (Genesis-054 Sprint-001).
    from core.mission.registry import MissionRegistry
    project_root     = Path(__file__).resolve().parents[2]  # jarvis3/
    mission_registry = MissionRegistry(project_root=project_root)
    mission_registry.load()
    logger.info("[SERVER] MissionRegistry loaded.")

    # Step 3d -- Inject MissionRegistry into SuiteRunnerWorker.
    try:
        suite_worker = agent.worker_manager.get_worker("suite_runner_worker")
        if suite_worker is not None:
            suite_worker._mission_registry = mission_registry
            logger.info("[SERVER] MissionRegistry injected into SuiteRunnerWorker.")
        else:
            logger.warning("[SERVER] SuiteRunnerWorker not found — MissionRegistry not injected.")
    except Exception as e:
        logger.warning("[SERVER] Could not inject MissionRegistry into SuiteRunnerWorker: %s", e)

    # Step 3e -- Create Engineering Coordinator for orchestrator approval workflow.
    from core.engineering.coordinator.coordinator import EngineeringCoordinator
    from core.engineering.coordinator.session_store import SessionStore
    from core.ai_workers.claude_worker import ClaudeAIWorker
    from core.engineering.execution.execution_runner import ExecutionRunner
    session_store    = SessionStore()
    claude_worker    = ClaudeAIWorker(ai_client=ai)
    execution_runner = ExecutionRunner(
        worker_coordinator=agent.worker_coordinator,
        worker_manager=agent.worker_manager,
        worker_intelligence=getattr(agent, "worker_intelligence", None),
    )
    from core.engineering.guardrails.guardrails import EngineeringGuardrails
    from core.engineering.coordinator.coordinator import CoordinatorConfig
    guardrails   = EngineeringGuardrails()
    coord_config = CoordinatorConfig(
        enable_planning=False,
        enable_guardrails=True,
        enable_approval_gate=True,
        enable_validation=False,
        enable_debugging=False,
        enable_repair=False,
    )
    orchestrator = EngineeringCoordinator(
        config=coord_config,
        session_store=session_store,
        claude_worker=claude_worker,
        execution_runner=execution_runner,
        guardrails=guardrails,
    )
    logger.info("[SERVER] EngineeringCoordinator initialised with Claude + ExecutionRunner.")

    # Step 3f -- Create MissionPipeline (Genesis-055 Sprint-001).
    from core.mission.pipeline import MissionPipeline
    mission_pipeline = MissionPipeline(mission_registry=mission_registry, project_root=project_root)
    logger.info("[SERVER] MissionPipeline initialised.")

    # Step 4 -- Create Flask app and inject the agent.
    from apps.server.app import create_app
    app = create_app(
        agent,
        system_registry=system_registry,
        session_registry=session_registry,
        orchestrator_coordinator=orchestrator,
        mission_registry=mission_registry,
        mission_pipeline=mission_pipeline,
    )

    # Configuration via environment with sensible defaults.
    host  = os.getenv("JARVISS_SERVER_HOST", "0.0.0.0")
    port  = int(os.getenv("JARVIS_SERVER_PORT", "5001"))
    debug = os.getenv("JARVIS_SERVER_DEBUG", "false").lower() == "true"
    logger.info("[SERVER] Starting Jarvis API on %s:%s", host, port)
    app.run(host=host, port=port, debug=debug)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
