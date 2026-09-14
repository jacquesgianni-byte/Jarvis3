"""
Genesis-081 Sprint-003 — Regression tests for GREETING intent fix.

Two groups:

    GROUP A — Must still return Intent.GREETING
        Standalone greetings, with or without "Jarvis" address.
        These must never regress.

    GROUP B — Must NOT return Intent.GREETING
        Wake-word openers followed by substantive content.
        These were previously mis-classified as GREETING — this is the fix.

    GROUP C — Genesis-012 regression guard
        The original "which"/"hi" substring bug must remain fixed.
"""

import pytest

from core.router import IntentRouter
from core.intents import Intent


@pytest.fixture(scope="module")
def router():
    return IntentRouter()


# ---------------------------------------------------------------------------
# GROUP A: genuine standalone greetings — must return GREETING
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "hey",
    "hey!",
    "Hey",
    "HEY",
    "hello",
    "Hello",
    "Hello!",
    "hi",
    "Hi",
    "Hi!",
    "good morning",
    "Good morning",
    "Good Morning!",
    "good afternoon",
    "good evening",
    "hey jarvis",
    "Hey Jarvis",
    "Hey Jarvis!",
    "Hello Jarvis",
    "Hello Jarvis!",
    "Hi Jarvis",
    "hi jarvis!",
    "good morning jarvis",
    "Good morning, Jarvis!",
    "hey jarvis.",
    # Filler words after greeting opener — must still be GREETING
    "hey there",
    "Hey there",
    "Hey there!",
    "hi there",
    "Hi there!",
    "hello again",
    "hey back",
])
def test_standalone_greeting_still_routes_to_greeting(router, message):
    """GROUP A: pure greetings must still return Intent.GREETING."""
    result = router.detect(message)
    assert result == Intent.GREETING, (
        f"Expected GREETING for {message!r}, got {result}"
    )


# ---------------------------------------------------------------------------
# GROUP B: wake-word opener + substantive content — must NOT return GREETING
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    # The exact incident trigger
    "Hey Jarvis, I'm home. I've got a few things to get done today. What do you think I should focus on first?",
    # Variants
    "Hey Jarvis, what should I focus on today?",
    "Hey Jarvis, I need your help with something.",
    "Hello, what's the weather like?",
    "Hello Jarvis, can you remind me what I said about the dogs?",
    "Hi, can you remind me what I said about the project?",
    "Good morning, I've got a lot on today.",
    "Good morning Jarvis, let's get started.",
    "Hey, I need to think through something.",
    "Hi there, what do you know about my schedule?",
    "Hello, I have two dogs.",
    "Hey Jarvis, I'm thinking of taking a trip next year.",
])
def test_wake_word_with_content_does_not_route_to_greeting(router, message):
    """GROUP B: greeting opener + substantive content must NOT be GREETING."""
    result = router.detect(message)
    assert result != Intent.GREETING, (
        f"Expected NOT GREETING for {message!r}, got {result}"
    )


# ---------------------------------------------------------------------------
# GROUP C: Genesis-012 regression guard — \bhey\b inside other words
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "Which weighs more, a pound of feathers or a pound of gold?",
    "which weighs more",
])
def test_genesis012_regression_which_not_greeting(router, message):
    """GROUP C: Genesis-012 regression — 'which' must not match 'hi'."""
    result = router.detect(message)
    assert result != Intent.GREETING, (
        f"Genesis-012 regression: expected NOT GREETING for {message!r}, got {result}"
    )


# ---------------------------------------------------------------------------
# GROUP D: memory queries starting with a greeting word still hit MEMORY
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("message", [
    "Hello, do you remember my name?",
])
def test_memory_queries_with_greeting_opener_route_to_memory(router, message):
    """GROUP D: MEMORY patterns checked before GREETING — must still route to MEMORY."""
    result = router.detect(message)
    assert result == Intent.MEMORY, (
        f"Expected MEMORY for {message!r}, got {result}"
    )
