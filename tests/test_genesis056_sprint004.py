"""
Genesis-056 Sprint-004 ? IntentStage whole-word matching regression tests.

Proves:
    - "do not make any changes" -> intent = investigate (not write)
    - "change project_state.json" -> intent = write
    - "investigate whether..." -> intent = investigate
    - "changes" does not match "change" write keyword
    - "updated" does not match "update" write keyword
    - "committed" does not match "commit" write keyword
"""
import pytest
from unittest.mock import MagicMock
from core.mission.pipeline import IntentStage, MissionRequest
from core.mission.context import MissionContext, InterfaceMode


def make_request(message: str) -> MissionRequest:
    ctx = MissionContext.for_mission(
        session_id="test",
        permitted_workers=frozenset(),
        knowledge_categories=frozenset(),
    )
    return MissionRequest(message=message, session_id="test", context=ctx)


class TestWholeWordMatching:

    def setup_method(self):
        self.stage = IntentStage()

    def _intent(self, message: str) -> str:
        state = {}
        self.stage.run(make_request(message), state)
        return state["intent"]

    # ?? The exact failing message ??????????????????????????????????????????

    def test_investigate_with_no_changes_phrase_is_investigate(self):
        msg = (
            "Investigate whether Mission Control can currently tell me what we "
            "should work on next. If it can't, determine the smallest safe "
            "improvement needed and prepare a proposal for Claude to implement. "
            "Do not make any changes without my approval."
        )
        assert self._intent(msg) == "investigate"

    # ?? "changes" must not match "change" ?????????????????????????????????

    def test_changes_does_not_trigger_write(self):
        assert self._intent("do not make any changes") == "unknown"

    def test_change_alone_triggers_write(self):
        assert self._intent("change project_state.json") == "write"

    def test_investigate_keyword_wins_over_changes(self):
        assert self._intent("investigate the changes") == "investigate"

    # ?? Other substring false positives fixed ??????????????????????????????

    def test_updated_does_not_trigger_write(self):
        assert self._intent("the file was updated yesterday") == "unknown"

    def test_update_alone_triggers_write(self):
        assert self._intent("update project_state.json") == "write"

    def test_committed_does_not_trigger_write(self):
        assert self._intent("we committed the fix") == "unknown"

    def test_commit_alone_triggers_write(self):
        assert self._intent("commit the changes") == "write"

    def test_deleted_does_not_trigger_write(self):
        assert self._intent("the file was deleted") == "unknown"

    def test_delete_alone_triggers_write(self):
        assert self._intent("delete that file") == "write"

    # ?? Investigate keywords still work ????????????????????????????????????

    def test_investigate_keyword_detected(self):
        assert self._intent("investigate why the genesis is wrong") == "investigate"

    def test_why_is_keyword_detected(self):
        assert self._intent("why is mission control showing the wrong genesis") == "investigate"

    def test_diagnose_keyword_detected(self):
        assert self._intent("diagnose the stale state") == "investigate"

    # ?? Write keywords still work ??????????????????????????????????????????

    def test_modify_triggers_write(self):
        assert self._intent("modify the pipeline") == "write"

    def test_write_triggers_write(self):
        assert self._intent("write a new file") == "write"

    def test_push_triggers_write(self):
        assert self._intent("push to main") == "write"
