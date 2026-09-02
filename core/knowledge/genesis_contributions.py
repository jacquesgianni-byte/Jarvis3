"""
Jarvis OS - GenesisContributionStore - Genesis-068 Sprint-002

Append-only log of agent contributions at Genesis scope.

Design invariants:
    - Agent identity is always resolved server-side from X-Agent-Token.
      No self-declared agent field is accepted.
    - Every write is validated against _AUTHORITY_TABLE before appending.
      An agent may only write roles declared for it in that table.
    - The contribution log is append-only. No entry is ever deleted or mutated.
    - One JSON file per genesis_id at data/genesis_contributions/<genesis_id>.json
    - resolve_agent_from_request() is the single point of identity resolution
      for HTTP callers. Non-HTTP callers pass agent identity directly.
    - GenesisContributionStore never reads HTTP requests itself.
"""
from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Authority table — who may write, and which roles they may claim
# ---------------------------------------------------------------------------

_AUTHORITY_TABLE: dict[str, tuple[str, ...]] = {
    "claude":  ("implementation", "critique"),
    "gpt":     ("architecture",   "critique"),
    "jarvis":  ("execution",      "observation"),
    "chief":   ("decision",       "observation"),
}

# Env vars that back each agent identity
_AGENT_ENV_VARS: dict[str, str] = {
    "gpt":    "AGENT_TOKEN_GPT",
    "claude": "AGENT_TOKEN_CLAUDE",
    "jarvis": "AGENT_TOKEN_JARVIS",
    "chief":  "ORCHESTRATOR_TOKEN",
}


# ---------------------------------------------------------------------------
# GenesisContribution — immutable record of one agent contribution
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class GenesisContribution:
    """
    Immutable record of one agent contribution at Genesis scope.

    contribution_id: unique identifier (UUID4)
    genesis_id:      which Genesis this contribution belongs to
    agent:           resolved agent identity (never self-declared)
    role:            the contribution role (must be in _AUTHORITY_TABLE)
    summary:         one-sentence description of the contribution
    artifact:        optional reference to the artifact produced (URL, path, or description)
    timestamp:       ISO-8601 UTC timestamp of the contribution
    """
    contribution_id: str
    genesis_id:      str
    agent:           str
    role:            str
    summary:         str
    artifact:        str
    timestamp:       str

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict) -> "GenesisContribution":
        return cls(
            contribution_id = d["contribution_id"],
            genesis_id      = d["genesis_id"],
            agent           = d["agent"],
            role            = d["role"],
            summary         = d["summary"],
            artifact        = d.get("artifact", ""),
            timestamp       = d["timestamp"],
        )


# ---------------------------------------------------------------------------
# Authority check
# ---------------------------------------------------------------------------

def _check_authority(agent: str, role: str) -> Optional[str]:
    """
    Return None if agent may write role. Return error string if not.
    """
    permitted_roles = _AUTHORITY_TABLE.get(agent)
    if permitted_roles is None:
        return f"Unknown agent {agent!r}. Permitted agents: {list(_AUTHORITY_TABLE)}"
    if role not in permitted_roles:
        return (
            f"Agent {agent!r} may not claim role {role!r}. "
            f"Permitted roles for {agent!r}: {list(permitted_roles)}"
        )
    return None


# ---------------------------------------------------------------------------
# HTTP identity resolution helper
# ---------------------------------------------------------------------------

def resolve_agent_from_request(request) -> Optional[str]:
    """
    Resolve agent identity from X-Agent-Token header.

    Checks the provided token against each agent's env-var-backed token.
    Returns the agent name if a match is found, None otherwise.

    Call this in route handlers before passing agent to GenesisContributionStore.
    The store never touches HTTP requests itself.
    """
    provided = request.headers.get("X-Agent-Token", "")
    if not provided:
        # Also try orchestrator token for Chief
        provided = request.headers.get("X-Orchestrator-Token", "")
        if provided:
            expected_chief = os.getenv("ORCHESTRATOR_TOKEN", "")
            if expected_chief and provided == expected_chief:
                return "chief"
        return None

    for agent, env_var in _AGENT_ENV_VARS.items():
        expected = os.getenv(env_var, "")
        if expected and provided == expected:
            return agent

    return None


# ---------------------------------------------------------------------------
# ContributeResult
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class ContributeResult:
    success:         bool
    contribution_id: str = ""
    error:           str = ""


# ---------------------------------------------------------------------------
# GenesisContributionStore
# ---------------------------------------------------------------------------

class GenesisContributionStore:
    """
    Append-only store for agent contributions at Genesis scope.

    One JSON file per genesis_id at data/genesis_contributions/<genesis_id>.json
    Every write is authority-checked before appending.
    Reads never fail — unknown genesis_id returns empty list.
    """

    def __init__(self, data_dir: Path) -> None:
        self._dir = data_dir / "genesis_contributions"
        self._dir.mkdir(parents=True, exist_ok=True)

    def contribute(
        self,
        genesis_id: str,
        agent:      str,
        role:       str,
        summary:    str,
        artifact:   str = "",
    ) -> ContributeResult:
        """
        Append one contribution to the Genesis log.

        agent must be a resolved identity string — never self-declared.
        Call resolve_agent_from_request() in the route handler first.

        Returns ContributeResult(success=True, contribution_id=...) on success.
        Returns ContributeResult(success=False, error=...) on authority failure or persist failure.
        """
        # Authority check
        err = _check_authority(agent, role)
        if err:
            logger.warning("[GenesisContributionStore] Authority denied: %s", err)
            return ContributeResult(success=False, error=err)

        contribution = GenesisContribution(
            contribution_id = str(uuid.uuid4()),
            genesis_id      = genesis_id,
            agent           = agent,
            role            = role,
            summary         = summary,
            artifact        = artifact,
            timestamp       = datetime.now(timezone.utc).isoformat(),
        )

        try:
            existing = self._load_raw(genesis_id)
            existing.append(contribution.to_dict())
            self._persist(genesis_id, existing)
        except Exception as e:
            logger.warning(
                "[GenesisContributionStore] Persist failed for %s: %s", genesis_id, e
            )
            return ContributeResult(success=False, error=f"Persist failed: {e}")

        logger.info(
            "[GenesisContributionStore] %s contributed %r to %s (id=%s)",
            agent, role, genesis_id, contribution.contribution_id[:8],
        )
        return ContributeResult(success=True, contribution_id=contribution.contribution_id)

    def get_contributions(self, genesis_id: str) -> List[GenesisContribution]:
        """
        Return all contributions for genesis_id in append order.
        Returns empty list if no contributions exist — never raises.
        """
        raw = self._load_raw(genesis_id)
        result = []
        for d in raw:
            try:
                result.append(GenesisContribution.from_dict(d))
            except Exception as e:
                logger.warning(
                    "[GenesisContributionStore] Skipping malformed entry for %s: %s",
                    genesis_id, e,
                )
        return result

    def permitted_roles(self, agent: str) -> tuple:
        """Return the permitted roles for agent, or empty tuple if unknown."""
        return _AUTHORITY_TABLE.get(agent, ())

    def known_agents(self) -> list:
        """Return the list of known agents."""
        return list(_AUTHORITY_TABLE)

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    def _load_raw(self, genesis_id: str) -> list:
        path = self._path_for(genesis_id)
        if not path.exists():
            return []
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            logger.warning(
                "[GenesisContributionStore] Could not read %s: %s", path, e
            )
            return []

    def _persist(self, genesis_id: str, entries: list) -> None:
        path = self._path_for(genesis_id)
        path.write_text(json.dumps(entries, indent=2), encoding="utf-8")

    def _path_for(self, genesis_id: str) -> Path:
        safe = "".join(c for c in genesis_id if c.isalnum() or c in "-_")
        return self._dir / f"{safe}.json"
