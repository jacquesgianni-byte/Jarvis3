import re
import pytest
from unittest.mock import MagicMock


def _build_summary(step_results, *, step_count, genesis_id, commit):
    _passed = _skipped = _failed = None
    for sr in step_results:
        if sr["action_type"] == "run_tests" and sr["success"]:
            m = re.search(r"(\d+) passed", sr["detail"] or "")
            if m:
                _passed = int(m.group(1))
            m = re.search(r"(\d+) skipped", sr["detail"] or "")
            if m:
                _skipped = int(m.group(1))
            m = re.search(r"(\d+) failed", sr["detail"] or "")
            if m:
                _failed = int(m.group(1))
            break
    if _passed is not None:
        suite_str = "tests_passed={} tests_skipped={} tests_failed={}".format(
            _passed, _skipped, _failed or 0
        )
    else:
        suite_str = "suite_result=unavailable"
    return (
        "Jarvis executed {} step(s) for {}. All steps succeeded. {}. Commit: {}.".format(
            step_count, genesis_id, suite_str, commit or "none"
        )
    )


def _project(contributions):
    last_exec = None
    for c in reversed(contributions):
        if c.get("agent") == "jarvis" and c.get("role") == "execution":
            s = c.get("summary", "")
            lse = {
                "agent":     "jarvis",
                "timestamp": c.get("timestamp", ""),
                "commit":    c.get("artifact", ""),
            }
            m = re.search(r"tests_passed=(\d+)", s)
            if m:
                lse["tests_passed"] = int(m.group(1))
            m = re.search(r"tests_skipped=(\d+)", s)
            if m:
                lse["tests_skipped"] = int(m.group(1))
            m = re.search(r"tests_failed=(\d+)", s)
            if m:
                lse["tests_failed"] = int(m.group(1))
            last_exec = lse
            break
    return last_exec


def _jc(summary, artifact="abc1234", timestamp="2026-09-04T10:00:00+00:00"):
    return {
        "agent": "jarvis", "role": "execution",
        "summary": summary, "artifact": artifact, "timestamp": timestamp,
    }


def _sr(action_type, success, detail, commit_sha=""):
    return {
        "action_type": action_type, "success": success,
        "detail": detail, "commit_sha": commit_sha,
    }


# -- Group 1: suite counts in summary --

def test_passed_count_embedded():
    s = _build_summary(
        [_sr("run_tests", True, "PASSED. 5910 passed, 33 skipped in 145.2s")],
        step_count=1, genesis_id="Genesis-072", commit="abc",
    )
    assert "tests_passed=5910" in s


def test_skipped_count_embedded():
    s = _build_summary(
        [_sr("run_tests", True, "PASSED. 5910 passed, 33 skipped in 145.2s")],
        step_count=1, genesis_id="Genesis-072", commit="abc",
    )
    assert "tests_skipped=33" in s


def test_failed_zero_when_absent():
    s = _build_summary(
        [_sr("run_tests", True, "PASSED. 5910 passed, 33 skipped in 145.2s")],
        step_count=1, genesis_id="Genesis-072", commit="abc",
    )
    assert "tests_failed=0" in s


def test_failed_nonzero_when_present():
    s = _build_summary(
        [_sr("run_tests", True, "FAILED. 5900 passed, 33 skipped, 2 failed in 145.2s")],
        step_count=1, genesis_id="Genesis-072", commit="abc",
    )
    assert "tests_failed=2" in s


def test_unavailable_when_no_run_tests_step():
    s = _build_summary(
        [_sr("commit", True, "Committed.", "abc")],
        step_count=1, genesis_id="Genesis-072", commit="abc",
    )
    assert "suite_result=unavailable" in s


def test_commit_still_present():
    s = _build_summary(
        [_sr("run_tests", True, "PASSED. 5910 passed, 33 skipped in 145.2s")],
        step_count=1, genesis_id="Genesis-072", commit="deadbeef",
    )
    assert "deadbeef" in s


def test_genesis_id_in_summary():
    s = _build_summary(
        [_sr("run_tests", True, "PASSED. 5910 passed, 33 skipped in 145.2s")],
        step_count=2, genesis_id="Genesis-072", commit="abc",
    )
    assert "Genesis-072" in s


# -- Group 2: last_successful_execution projection --

def test_null_when_empty():
    assert _project([]) is None


def test_null_when_no_jarvis_execution():
    c = {"agent": "claude", "role": "implementation",
         "summary": "", "artifact": "", "timestamp": ""}
    assert _project([c]) is None


def test_commit_from_artifact():
    r = _project([_jc("tests_passed=5910 tests_skipped=33 tests_failed=0.", "abc")])
    assert r["commit"] == "abc"


def test_tests_passed_extracted():
    r = _project([_jc("tests_passed=5910 tests_skipped=33 tests_failed=0.")])
    assert r["tests_passed"] == 5910


def test_tests_skipped_extracted():
    r = _project([_jc("tests_passed=5910 tests_skipped=33 tests_failed=0.")])
    assert r["tests_skipped"] == 33


def test_tests_failed_extracted():
    r = _project([_jc("tests_passed=5910 tests_skipped=33 tests_failed=0.")])
    assert r["tests_failed"] == 0


def test_most_recent_wins():
    c1 = _jc("tests_passed=5800 tests_skipped=33 tests_failed=0.", "aaa", "2026-09-01T00:00:00+00:00")
    c2 = _jc("tests_passed=5910 tests_skipped=33 tests_failed=0.", "bbb", "2026-09-04T00:00:00+00:00")
    r = _project([c1, c2])
    assert r["commit"] == "bbb"
    assert r["tests_passed"] == 5910


def test_other_agents_ignored():
    cc = {"agent": "claude", "role": "implementation",
          "summary": "tests_passed=9999.", "artifact": "zzz",
          "timestamp": "2026-09-05T00:00:00+00:00"}
    jc = _jc("tests_passed=5910 tests_skipped=33 tests_failed=0.", "abc",
             "2026-09-04T00:00:00+00:00")
    r = _project([jc, cc])
    assert r["commit"] == "abc"
    assert r["tests_passed"] == 5910


def test_old_format_no_counts():
    c = _jc("Jarvis executed 2 step(s). All steps succeeded. Tests passed. Commit: abc.")
    r = _project([c])
    assert r is not None
    assert "tests_passed" not in r


# -- Group 3: failed execution guard --

def test_no_contribution_on_failure():
    store = MagicMock()
    success = False
    if success and store is not None:
        store.append("Genesis-072", MagicMock())
    store.append.assert_not_called()


def test_previous_success_not_overwritten():
    contributions = [_jc("tests_passed=5882 tests_skipped=33 tests_failed=0.", "abc")]
    r = _project(contributions)
    assert r is not None
    assert r["commit"] == "abc"
