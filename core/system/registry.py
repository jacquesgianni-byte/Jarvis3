"""
Jarvis OS System Registry — Genesis-054 Sprint-001

Runtime health only. Project identity is owned by MissionRegistry.
"""
from __future__ import annotations

import platform
import time
from dataclasses import dataclass

JARVIS_VERSION = "0.1-alpha"
JARVIS_BUILD   = "Genesis-054"

_server_start_time = time.time()


@dataclass
class SystemState:
    status:          str   = "online"
    version:         str   = JARVIS_VERSION
    build:           str   = JARVIS_BUILD
    python:          str   = ""
    os_name:         str   = ""
    uptime_seconds:  float = 0.0
    uptime_human:    str   = ""
    workers_online:  int   = 0
    memory_records:  int   = 0
    memory_status:   str   = "unknown"
    ai_provider:     str   = "none"
    skills_loaded:   int   = 0
    processing:      bool  = False


@dataclass
class EngineeringState:
    pending_review:  bool = False
    pending_commit:  bool = False
    pending_push:    bool = False
    workers_loaded:  int  = 0


def _uptime_human(seconds: float) -> str:
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, _   = divmod(rem, 60)
    if h > 0:
        return f"{h}h {m}m"
    return f"{m}m"


class SystemRegistry:
    """
    Live runtime health registry.
    Injected with the Agent at startup so it can read live data.
    Project identity (genesis, tests, commit) is owned by MissionRegistry.
    """

    def __init__(self, agent=None):
        self._agent = agent
        self._start = _server_start_time

    def get_system_state(self) -> SystemState:
        uptime = time.time() - self._start
        state  = SystemState(
            python         = platform.python_version(),
            os_name        = platform.system(),
            uptime_seconds = uptime,
            uptime_human   = _uptime_human(uptime),
        )
        if self._agent:
            try:
                state.workers_online = self._agent.worker_manager.worker_count()
            except Exception:
                pass
            try:
                count = self._agent.knowledge.count()
                state.memory_records = count
                state.memory_status  = "healthy" if count > 0 else "empty"
            except Exception:
                state.memory_status = "unknown"
            try:
                state.ai_provider = self._agent.ai.active_provider_name()
            except Exception:
                pass
            try:
                state.skills_loaded = len(self._agent.skills._skills)
            except Exception:
                pass
        return state

    def get_engineering_state(self) -> EngineeringState:
        state = EngineeringState()
        if self._agent:
            try:
                state.workers_loaded = self._agent.worker_manager.worker_count()
            except Exception:
                pass
            try:
                state.pending_commit = self._agent.execution_runner.has_pending_commit()
                state.pending_push   = self._agent.execution_runner.has_pending_push()
            except Exception:
                pass
        return state

    def system_dict(self) -> dict:
        s = self.get_system_state()
        return {
            "status":         s.status,
            "version":        s.version,
            "build":          s.build,
            "python":         s.python,
            "os":             s.os_name,
            "uptime_seconds": round(s.uptime_seconds),
            "uptime":         s.uptime_human,
            "workers_online": s.workers_online,
            "memory_records": s.memory_records,
            "memory_status":  s.memory_status,
            "ai_provider":    s.ai_provider,
            "skills_loaded":  s.skills_loaded,
        }

    def engineering_dict(self) -> dict:
        e = self.get_engineering_state()
        return {
            "pending_review": e.pending_review,
            "pending_commit": e.pending_commit,
            "pending_push":   e.pending_push,
            "workers_loaded": e.workers_loaded,
        }
