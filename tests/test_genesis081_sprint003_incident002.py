"""
Genesis-081 Sprint-003 — Incident #002 regression tests.

Verifies that _TEMPORAL_TODAY in ConversationRecall.can_answer() requires
an explicit recall-shaped question. Passive uses of 'today' must not trigger
journal recall.
"""

import pytest
from core.conversation.conversation_recall import ConversationRecall
from core.knowledge_engine.engine import KnowledgeEngine


@pytest.fixture(scope="module")
def recall():
    """ConversationRecall with a real (empty) KnowledgeEngine."""
    from core.knowledge_engine.json_storage import JsonKnowledgeRepository
    import tempfile, pathlib
    tmp = pathlib.Path(tempfile.mkdtemp()) / "knowledge.json"
    tmp.write_text("[]", encoding="utf-8")
    repo = JsonKnowledgeRepository(path=str(tmp))
    ke = KnowledgeEngine(storage=repo)
    return ConversationRecall(ke)


# ---------------------------------------------------------------------------
# Positive: 'today' + explicit recall pattern -> can_answer() must be True
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    # Existing recall patterns + today
    "What did we finish today?",
    "What are we working on today?",
    "What milestone did we complete today?",
    "What project are we doing today?",
    # General activity today -- covered by _GENERAL_TODAY_QUERY
    "What did we do today?",
    "What did we discuss today?",
    "What did we talk about today?",
    "What did we work on today?",
    "What did we accomplish today?",
    "What happened today?",
])
def test_today_with_recall_pattern_can_answer(recall, query):
    """Legitimate today-recall queries must still be handled."""
    assert recall.can_answer(query), (
        f"Expected can_answer()=True for {query!r}"
    )


# ---------------------------------------------------------------------------
# Negative: 'today' without recall pattern -> can_answer() must be False
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("query", [
    # The exact incident trigger
    "Hey Jarvis, I'm home. I've got a few things to get done today. What do you think I should focus on first?",
    # Variants
    "What should I focus on today?",
    "I'm busy today.",
    "Today was difficult.",
    "I'm travelling today.",
    "I've got a lot on today.",
    "I need to get some things done today.",
    "What do I need to do today?",
    "What should I do today?",
])
def test_passive_today_does_not_trigger_recall(recall, query):
    """Passive uses of 'today' must NOT trigger journal recall."""
    assert not recall.can_answer(query), (
        f"Expected can_answer()=False for {query!r}"
    )
