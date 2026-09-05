
import os, sys, pathlib, pytest

ROOT = pathlib.Path(r"C:\Users\ljmas\Desktop\jarvis3")
sys.path.insert(0, str(ROOT))

os.environ.setdefault("AGENT_TOKEN_GPT",    "JarvisGPT-Read-2024#")
os.environ.setdefault("AGENT_TOKEN_CLAUDE", "JarvisClaude-RW-2024#")
os.environ.setdefault("AGENT_TOKEN_JARVIS", "JarvisInternal-2024#")
os.environ.setdefault("ORCHESTRATOR_TOKEN", "Lucasleo2104#")

_TOKENS = {
    "claude": os.environ["AGENT_TOKEN_CLAUDE"],
    "gpt":    os.environ["AGENT_TOKEN_GPT"],
    "jarvis": os.environ["AGENT_TOKEN_JARVIS"],
    "chief":  os.environ["ORCHESTRATOR_TOKEN"],
}

@pytest.fixture(scope="module")
def app():
    import os
    from unittest.mock import MagicMock
    from apps.server.app import create_app
    # Force-set tokens in case an earlier test module cleared or overwrote them
    os.environ["AGENT_TOKEN_GPT"]    = "JarvisGPT-Read-2024#"
    os.environ["AGENT_TOKEN_CLAUDE"] = "JarvisClaude-RW-2024#"
    os.environ["AGENT_TOKEN_JARVIS"] = "JarvisInternal-2024#"
    os.environ["ORCHESTRATOR_TOKEN"] = "Lucasleo2104#"
    application = create_app(agent=MagicMock())
    application.config["TESTING"] = True
    return application

@pytest.fixture(scope="module")
def client(app):
    return app.test_client()

def _agent_headers(agent):
    if agent == "chief":
        return {"X-Orchestrator-Token": _TOKENS["chief"]}
    return {"X-Agent-Token": _TOKENS[agent]}

def _contribute(client, agent, genesis_id, role, summary="Test summary.", artifact=""):
    headers = {**_agent_headers(agent), "Content-Type": "application/json"}
    return client.post("/genesis/contribute", json={
        "genesis_id": genesis_id, "role": role,
        "summary": summary, "artifact": artifact,
    }, headers=headers)

# ---------------------------------------------------------------------------
# P -- Positive: all valid agent/role combinations
# ---------------------------------------------------------------------------

class TestPositiveCases:
    def test_P01_claude_implementation(self, client):
        r = _contribute(client, "claude", "Genesis-071", "implementation", "Claude implementation.")
        assert r.status_code == 201
        d = r.get_json()
        assert d["ok"] is True and d["agent"] == "claude" and d["role"] == "implementation"

    def test_P02_claude_critique(self, client):
        r = _contribute(client, "claude", "Genesis-071", "critique", "Claude critique.")
        assert r.status_code == 201
        d = r.get_json()
        assert d["ok"] is True and d["agent"] == "claude" and d["role"] == "critique"

    def test_P03_gpt_architecture(self, client):
        r = _contribute(client, "gpt", "Genesis-071", "architecture", "GPT architecture.")
        assert r.status_code == 201
        d = r.get_json()
        assert d["ok"] is True and d["agent"] == "gpt" and d["role"] == "architecture"

    def test_P04_gpt_critique(self, client):
        r = _contribute(client, "gpt", "Genesis-071", "critique", "GPT critique.")
        assert r.status_code == 201
        d = r.get_json()
        assert d["ok"] is True and d["agent"] == "gpt" and d["role"] == "critique"

    def test_P05_jarvis_execution(self, client):
        r = _contribute(client, "jarvis", "Genesis-071", "execution", "Jarvis execution.")
        assert r.status_code == 201
        d = r.get_json()
        assert d["ok"] is True and d["agent"] == "jarvis" and d["role"] == "execution"

    def test_P06_jarvis_observation(self, client):
        r = _contribute(client, "jarvis", "Genesis-071", "observation", "Jarvis observation.")
        assert r.status_code == 201
        d = r.get_json()
        assert d["ok"] is True and d["agent"] == "jarvis" and d["role"] == "observation"

    def test_P07_chief_decision(self, client):
        r = _contribute(client, "chief", "Genesis-071", "decision", "Chief decision.")
        assert r.status_code == 201
        d = r.get_json()
        assert d["ok"] is True and d["agent"] == "chief" and d["role"] == "decision"

    def test_P08_chief_observation(self, client):
        r = _contribute(client, "chief", "Genesis-071", "observation", "Chief observation.")
        assert r.status_code == 201
        d = r.get_json()
        assert d["ok"] is True and d["agent"] == "chief" and d["role"] == "observation"

# ---------------------------------------------------------------------------
# N -- Negative: invalid role combinations
# ---------------------------------------------------------------------------

class TestNegativeCases:
    def test_N01_claude_architecture_forbidden(self, client):
        r = _contribute(client, "claude", "Genesis-071", "architecture", "Claude tries architecture.")
        assert r.status_code == 403
        assert r.get_json()["ok"] is False

    def test_N02_gpt_execution_forbidden(self, client):
        r = _contribute(client, "gpt", "Genesis-071", "execution", "GPT tries execution.")
        assert r.status_code == 403
        assert r.get_json()["ok"] is False

    def test_N03_jarvis_implementation_forbidden(self, client):
        r = _contribute(client, "jarvis", "Genesis-071", "implementation", "Jarvis tries implementation.")
        assert r.status_code == 403
        assert r.get_json()["ok"] is False

    def test_N04_chief_implementation_forbidden(self, client):
        r = _contribute(client, "chief", "Genesis-071", "implementation", "Chief tries implementation.")
        assert r.status_code == 403
        assert r.get_json()["ok"] is False

# ---------------------------------------------------------------------------
# A -- Auth boundary
# ---------------------------------------------------------------------------

class TestAuthBoundary:
    def test_A01_no_token(self, client):
        r = client.post("/genesis/contribute",
            json={"genesis_id": "Genesis-071", "role": "architecture", "summary": "test"},
            headers={"Content-Type": "application/json"})
        assert r.status_code == 401
        assert r.get_json()["ok"] is False

    def test_A02_unknown_token(self, client):
        r = client.post("/genesis/contribute",
            json={"genesis_id": "Genesis-071", "role": "architecture", "summary": "test"},
            headers={"Content-Type": "application/json", "X-Agent-Token": "not-a-real-token"})
        assert r.status_code == 401
        assert r.get_json()["ok"] is False

    def test_A03_gpt_token_genesis_contribution_201(self, client):
        """Key regression: GPT token + Genesis scope = 201. Proves Genesis-070 gap is closed."""
        r = _contribute(client, "gpt", "Genesis-071", "architecture",
                        summary="GPT architecture via correct Genesis interface.",
                        artifact="Genesis-071-architecture-review")
        assert r.status_code == 201
        d = r.get_json()
        assert d["ok"] is True and d["agent"] == "gpt" and d["role"] == "architecture"

# ---------------------------------------------------------------------------
# V -- Input validation
# ---------------------------------------------------------------------------

class TestInputValidation:
    def test_V01_missing_genesis_id(self, client):
        r = client.post("/genesis/contribute",
            json={"role": "architecture", "summary": "test"},
            headers={"Content-Type": "application/json", "X-Agent-Token": _TOKENS["gpt"]})
        assert r.status_code == 400
        assert "genesis_id" in r.get_json()["error"]

    def test_V02_missing_role(self, client):
        r = client.post("/genesis/contribute",
            json={"genesis_id": "Genesis-071", "summary": "test"},
            headers={"Content-Type": "application/json", "X-Agent-Token": _TOKENS["gpt"]})
        assert r.status_code == 400
        assert "role" in r.get_json()["error"]

    def test_V03_missing_summary(self, client):
        r = client.post("/genesis/contribute",
            json={"genesis_id": "Genesis-071", "role": "architecture"},
            headers={"Content-Type": "application/json", "X-Agent-Token": _TOKENS["gpt"]})
        assert r.status_code == 400
        assert "summary" in r.get_json()["error"]

    def test_V04_artifact_optional_defaults_empty(self, client):
        r = client.post("/genesis/contribute",
            json={"genesis_id": "Genesis-071", "role": "critique", "summary": "No artifact."},
            headers={"Content-Type": "application/json", "X-Agent-Token": _TOKENS["gpt"]})
        assert r.status_code == 201
        assert r.get_json()["ok"] is True

# ---------------------------------------------------------------------------
# R -- Persistence and read-back
# ---------------------------------------------------------------------------

class TestPersistence:
    def test_R01_contribute_then_read_back(self, client, app):
        genesis_id = "Genesis-071-readback"
        summary    = "Unique readback test contribution."
        artifact   = "readback-artifact-ref"
        r = _contribute(client, "claude", genesis_id, "implementation",
                        summary=summary, artifact=artifact)
        assert r.status_code == 201
        contribution_id = r.get_json()["contribution_id"]
        with app.app_context():
            store = app.config.get("genesis_contribution_store")
            assert store is not None
            contributions = store.get_contributions(genesis_id)
        match = next((c for c in contributions if c.contribution_id == contribution_id), None)
        assert match is not None
        assert match.agent      == "claude"
        assert match.role       == "implementation"
        assert match.summary    == summary
        assert match.artifact   == artifact
        assert match.genesis_id == genesis_id

# ---------------------------------------------------------------------------
# S -- Scope isolation
# ---------------------------------------------------------------------------

class TestScopeIsolation:
    def test_S01_genesis_contribute_does_not_touch_sprint_store(self, client, app):
        with app.app_context():
            sprint_store = app.config.get("sprint_state_store")
            if sprint_store is None:
                pytest.skip("sprint_state_store not available")
            before_counts = {}
            try:
                for record in sprint_store.all_active():
                    before_counts[record.proposal_id] = len(record.contributions)
            except Exception:
                pass
        r = _contribute(client, "gpt", "Genesis-071-isolation", "architecture", "Isolation test.")
        assert r.status_code == 201
        with app.app_context():
            sprint_store = app.config.get("sprint_state_store")
            for pid, before in before_counts.items():
                rec = sprint_store.load(pid)
                if rec:
                    assert len(rec.contributions) == before, \
                        f"SprintStateRecord {pid} was touched by Genesis contribute"

# ---------------------------------------------------------------------------
# X -- Regression
# ---------------------------------------------------------------------------

class TestRegression:
    def test_X01_get_genesis_still_returns_contributions(self, client, app):
        genesis_id = "Genesis-071-regression"
        r = _contribute(client, "claude", genesis_id, "implementation", "Regression test.")
        assert r.status_code == 201
        contribution_id = r.get_json()["contribution_id"]
        with app.app_context():
            store = app.config.get("genesis_contribution_store")
            if store:
                ids = [c.contribution_id for c in store.get_contributions(genesis_id)]
                assert contribution_id in ids

    def test_X02_body_agent_field_is_ignored(self, client):
        """Body-supplied agent field must be ignored; identity from token only."""
        r = client.post("/genesis/contribute",
            json={"genesis_id": "Genesis-071", "role": "implementation",
                  "summary": "Body agent ignored.", "agent": "gpt"},
            headers={"Content-Type": "application/json", "X-Agent-Token": _TOKENS["claude"]})
        assert r.status_code == 201
        assert r.get_json()["agent"] == "claude", "Body agent field was not ignored"
