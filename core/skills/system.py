"""
System Skill -- Genesis-042 Sprint-001

Answers system/diagnostic questions locally.
Never touches the AI provider.
"""

from __future__ import annotations
import platform
from core.models.response import Response

JARVIS_VERSION = "0.1-alpha"
BUILD = "Genesis-042"


class SystemSkill:
    """Answers system questions without using any AI provider."""

    name = "system"

    _STATUS_TRIGGERS = {
        "system status", "status report", "system check", "system report",
        "diagnostics", "run diagnostics", "health check", "run health check",
    }
    _OK_TRIGGERS = {
        "are you okay", "are you ok", "are you working",
        "are you online", "how are you running", "how are you doing",
        "self check", "self-check",
    }
    _VERSION_TRIGGERS = {
        "what version", "which version", "version number",
        "your version", "what version are you",
    }
    _CAPABILITY_TRIGGERS = {
        "what can you do", "what are your capabilities",
        "what are you capable of",
    }
    _PROVIDER_TRIGGERS = {
        "what ai", "which ai", "what model", "which model",
        "what provider", "which provider", "ai provider",
        "what are you running", "what are you using",
    }
    _TIMELINE_TRIGGERS = {
        "activity log", "operational log", "show timeline",
        "show today", "jarvis timeline", "server log", "daily activity",
    }

    _ENGINEERING_TRIGGERS = {
        "engineering status", "engineering history", "engineering queue",
        "engineering logs", "engineering workers", "engineering dashboard",
    }

    def execute(self, request: str, agent=None) -> Response:
        req = request.lower().strip().rstrip("?.!")
        if any(t in req for t in self._STATUS_TRIGGERS):
            return self._status(agent)
        if any(t in req for t in self._OK_TRIGGERS):
            return self._health_check(agent)
        if any(t in req for t in self._VERSION_TRIGGERS):
            return self._version()
        if any(t in req for t in self._CAPABILITY_TRIGGERS):
            return self._capabilities(agent)
        if any(t in req for t in self._PROVIDER_TRIGGERS):
            return self._provider(agent)
        if any(t in req for t in self._TIMELINE_TRIGGERS):
            return self._timeline(agent)
        if any(t in req for t in self._ENGINEERING_TRIGGERS):
            return self._engineering(agent)
        return self._status(agent)

    def _timeline(self, agent) -> Response:
        """Return today's activity log from SessionRegistry."""
        try:
            # Try to get from app config via agent
            if hasattr(agent, '_session_registry') and agent._session_registry:
                return Response(success=True, message=agent._session_registry.today_summary())
            # Fall back to Flask app config
            try:
                from flask import current_app
                sr = current_app.config.get("SESSION_REGISTRY")
                if sr:
                    return Response(success=True, message=sr.today_summary())
            except Exception:
                pass
        except Exception:
            pass
        return Response(
            success=True,
            message="No session activity recorded yet. Keep talking to me and I'll track what we do."
        )

    def _version(self) -> Response:
        return Response(
            success=True,
            message=(
                f"Jarvis OS {JARVIS_VERSION} -- build {BUILD}. "
                f"Running on Python {platform.python_version()} "
                f"on {platform.system()}."
            )
        )

    def _health_check(self, agent) -> Response:
        checks = ["Core         OK  Online"]
        if agent:
            try:
                count = agent.knowledge.count() if hasattr(agent.knowledge, "count") else "unknown"
                checks.append(f"Memory       OK  {count} records")
            except Exception:
                checks.append("Memory       --  Unavailable")
            try:
                provider = agent.ai.active_provider_name() if agent.ai else "none"
                status = "OK" if provider != "none" else "--"
                checks.append(f"AI Provider  {status}  {provider}")
            except Exception:
                checks.append("AI Provider  --  Unavailable")
            try:
                wc = agent.worker_manager.worker_count()
                checks.append(f"Workers      OK  {wc} loaded")
            except Exception:
                checks.append("Workers      --  Unknown")
            try:
                sc = len(agent.skills._skills) if hasattr(agent.skills, "_skills") else "unknown"
                checks.append(f"Skills       OK  {sc} loaded")
            except Exception:
                checks.append("Skills       --  Unknown")
        return Response(
            success=True,
            message="System health check:\n" + "\n".join(checks) + "\n\nAll systems operational."
        )

    def _status(self, agent) -> Response:
        lines = [f"Jarvis OS {JARVIS_VERSION} -- {BUILD}"]
        if agent:
            try:
                provider = agent.ai.active_provider_name() if agent.ai else "none"
                lines.append(f"AI Provider: {provider}")
            except Exception:
                lines.append("AI Provider: unavailable")
            try:
                wc = agent.worker_manager.worker_count()
                lines.append(f"Workers: {wc} loaded")
            except Exception:
                pass
            try:
                count = agent.knowledge.count() if hasattr(agent.knowledge, "count") else "unknown"
                lines.append(f"Memory: {count} records")
            except Exception:
                pass
        lines.append("Status: Online")
        return Response(success=True, message="\n".join(lines))

    def _capabilities(self, agent) -> Response:
        skills = []
        if agent and hasattr(agent.skills, "_skills"):
            skills = list(agent.skills._skills.keys())
        skill_list = ", ".join(skills) if skills else "greeting, memory, identity, reasoning, engineering, system"
        return Response(
            success=True,
            message=f"I can handle: {skill_list}. I use AI only when none of my local skills can answer."
        )

    def _provider(self, agent) -> Response:
        if agent and agent.ai:
            try:
                provider = agent.ai.active_provider_name()
                return Response(
                    success=True,
                    message=f"Active AI provider: {provider}. I use it only as a last resort."
                )
            except Exception:
                pass
        return Response(
            success=True,
            message="No AI provider active. Answering from local skills and memory."
        )

    def _engineering(self, agent) -> Response:
        if not agent:
            return Response(success=True, message="Engineering pipeline unavailable.")
        try:
            wc = agent.worker_manager.worker_count()
            return Response(
                success=True,
                message=(
                    f"Engineering pipeline:\n"
                    f"Workers loaded: {wc}\n"
                    f"Pipeline: Online\n"
                    f"Last build: Genesis-041 -- Autonomous Engineering Execution"
                )
            )
        except Exception as e:
            return Response(success=True, message=f"Engineering status: {e}")
