from core.health import health


def test_health_returns_ok_exact_payload():
    assert health() == {"status": "ok"}


def test_health_status_key_present_and_ok():
    payload = health()
    assert isinstance(payload, dict)
    assert payload.get("status") == "ok"
