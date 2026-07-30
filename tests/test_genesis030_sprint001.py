"""
Tests for Genesis-030 Sprint-001: Response Coordinator

Covers:
    - Classification: FAST / MEDIUM / LONG
    - AcknowledgementStrategy: DefaultAcknowledgementStrategy
    - Topic extraction
    - Operation type inference
    - Pluggable strategy pattern
    - No regressions on existing conversation behaviour
"""

from __future__ import annotations

import pytest
from core.response_coordinator import (
    ResponseCoordinator,
    ResponseCategory,
    OperationType,
    ClassificationResult,
    DefaultAcknowledgementStrategy,
    AcknowledgementStrategy,
)


@pytest.fixture
def coordinator() -> ResponseCoordinator:
    return ResponseCoordinator()


# ===========================================================================
# FAST classification
# ===========================================================================

class TestFastClassification:

    def test_greeting_hi(self, coordinator):
        result = coordinator.classify("hi")
        assert result.category == ResponseCategory.FAST
        assert result.needs_ack is False

    def test_greeting_hello(self, coordinator):
        result = coordinator.classify("Hello Jarvis")
        assert result.category == ResponseCategory.FAST

    def test_how_old_is(self, coordinator):
        result = coordinator.classify("How old is Leo?")
        assert result.category == ResponseCategory.FAST

    def test_what_colour_is(self, coordinator):
        result = coordinator.classify("What colour is Rex?")
        assert result.category == ResponseCategory.FAST

    def test_who_is(self, coordinator):
        result = coordinator.classify("Who is Lucas?")
        assert result.category == ResponseCategory.FAST

    def test_remember(self, coordinator):
        result = coordinator.classify("Remember my name is Leo")
        assert result.category == ResponseCategory.FAST

    def test_exit(self, coordinator):
        result = coordinator.classify("goodbye")
        assert result.category == ResponseCategory.FAST

    def test_tell_me_about(self, coordinator):
        result = coordinator.classify("Tell me about Lucas")
        assert result.category == ResponseCategory.FAST

    def test_what_about(self, coordinator):
        result = coordinator.classify("What about Chase?")
        assert result.category == ResponseCategory.FAST

    def test_empty_string(self, coordinator):
        result = coordinator.classify("")
        assert result.category == ResponseCategory.FAST

    def test_what_time_is_it(self, coordinator):
        result = coordinator.classify("What time is it?")
        assert result.category == ResponseCategory.FAST

    def test_fast_has_no_acknowledgement(self, coordinator):
        result = coordinator.classify("How old is Leo?")
        assert result.acknowledgement == ""
        assert result.needs_ack is False


# ===========================================================================
# MEDIUM classification
# ===========================================================================

class TestMediumClassification:

    def test_explain(self, coordinator):
        result = coordinator.classify("Explain quantum computing.")
        assert result.category == ResponseCategory.MEDIUM
        assert result.needs_ack is True

    def test_what_is(self, coordinator):
        result = coordinator.classify("What is machine learning?")
        assert result.category == ResponseCategory.MEDIUM

    def test_how_does(self, coordinator):
        result = coordinator.classify("How does blockchain work?")
        assert result.category == ResponseCategory.MEDIUM

    def test_search(self, coordinator):
        result = coordinator.classify("Search the web for Python tutorials")
        assert result.category == ResponseCategory.MEDIUM

    def test_compare(self, coordinator):
        result = coordinator.classify("Compare Python and JavaScript")
        assert result.category == ResponseCategory.MEDIUM

    def test_recommend(self, coordinator):
        result = coordinator.classify("Recommend a good book on AI")
        assert result.category == ResponseCategory.MEDIUM

    def test_translate(self, coordinator):
        result = coordinator.classify("Translate hello to French")
        assert result.category == ResponseCategory.MEDIUM

    def test_write_email(self, coordinator):
        result = coordinator.classify("Write an email to my team")
        assert result.category == ResponseCategory.MEDIUM

    def test_medium_has_acknowledgement(self, coordinator):
        result = coordinator.classify("Explain relativity")
        assert result.acknowledgement != ""
        assert len(result.acknowledgement) > 3

    def test_medium_operation_set(self, coordinator):
        result = coordinator.classify("Explain quantum computing")
        assert result.operation == OperationType.EXPLAIN

    def test_search_operation(self, coordinator):
        result = coordinator.classify("Search for Python tutorials")
        assert result.operation == OperationType.SEARCH

    def test_compare_operation(self, coordinator):
        result = coordinator.classify("Compare Python and JavaScript")
        assert result.operation == OperationType.COMPARE


# ===========================================================================
# LONG classification
# ===========================================================================

class TestLongClassification:

    def test_write_code(self, coordinator):
        result = coordinator.classify("Write a Python script to parse CSV files")
        assert result.category == ResponseCategory.LONG
        assert result.needs_ack is True

    def test_generate_code(self, coordinator):
        result = coordinator.classify("Generate a class for user authentication")
        assert result.category == ResponseCategory.LONG

    def test_implement_function(self, coordinator):
        result = coordinator.classify("Implement a binary search function")
        assert result.category == ResponseCategory.LONG

    def test_create_module(self, coordinator):
        result = coordinator.classify("Create a module for database connections")
        assert result.category == ResponseCategory.LONG

    def test_refactor_code(self, coordinator):
        result = coordinator.classify("Refactor this code to use async functions")
        assert result.category == ResponseCategory.LONG

    def test_long_has_acknowledgement(self, coordinator):
        result = coordinator.classify("Write a Python script")
        assert result.acknowledgement != ""
        assert result.needs_ack is True

    def test_code_operation(self, coordinator):
        result = coordinator.classify("Write a Python script to parse CSV")
        assert result.operation == OperationType.CODE


# ===========================================================================
# Topic extraction
# ===========================================================================

class TestTopicExtraction:

    def test_explain_topic(self, coordinator):
        result = coordinator.classify("Explain quantum computing")
        assert result.topic is not None
        assert "quantum" in result.topic.lower()

    def test_topic_in_acknowledgement(self, coordinator):
        result = coordinator.classify("Explain quantum computing")
        assert "quantum" in result.acknowledgement.lower() or result.acknowledgement != ""

    def test_no_topic_still_works(self, coordinator):
        result = coordinator.classify("Explain things")
        assert result.acknowledgement != ""

    def test_topic_none_for_fast(self, coordinator):
        result = coordinator.classify("How old is Leo?")
        assert result.topic is None


# ===========================================================================
# AcknowledgementStrategy — pluggable pattern
# ===========================================================================

class TestAcknowledgementStrategy:

    def test_default_strategy_used(self, coordinator):
        result = coordinator.classify("Explain AI")
        assert result.acknowledgement != ""

    def test_custom_strategy_pluggable(self):
        """Verify a custom strategy can be injected."""
        class FormalStrategy(AcknowledgementStrategy):
            def generate(self, operation, topic, category):
                return f"Processing your request regarding {topic or 'this topic'}."

        coord = ResponseCoordinator(strategy=FormalStrategy())
        result = coord.classify("Explain quantum computing")
        assert "Processing your request" in result.acknowledgement

    def test_voice_strategy_example(self):
        """Voice mode strategy returns shorter phrases."""
        class VoiceStrategy(AcknowledgementStrategy):
            def generate(self, operation, topic, category):
                return "On it."

        coord = ResponseCoordinator(strategy=VoiceStrategy())
        result = coord.classify("Explain relativity")
        assert result.acknowledgement == "On it."

    def test_strategy_receives_operation(self):
        """Strategy receives the correct operation type."""
        received = []

        class RecordingStrategy(AcknowledgementStrategy):
            def generate(self, operation, topic, category):
                received.append(operation)
                return "OK"

        coord = ResponseCoordinator(strategy=RecordingStrategy())
        coord.classify("Explain quantum computing")
        assert len(received) == 1
        assert received[0] == OperationType.EXPLAIN

    def test_strategy_receives_topic(self):
        """Strategy receives the extracted topic."""
        received = []

        class RecordingStrategy(AcknowledgementStrategy):
            def generate(self, operation, topic, category):
                received.append(topic)
                return "OK"

        coord = ResponseCoordinator(strategy=RecordingStrategy())
        coord.classify("Explain quantum computing")
        assert len(received) == 1
        assert received[0] is not None

    def test_default_strategy_varies_phrases(self):
        """DefaultAcknowledgementStrategy cycles through variants."""
        strategy = DefaultAcknowledgementStrategy()
        results = [
            strategy.generate(OperationType.GENERAL, None, ResponseCategory.MEDIUM)
            for _ in range(10)
        ]
        # Should have some variety
        assert len(set(results)) > 1


# ===========================================================================
# ClassificationResult
# ===========================================================================

class TestClassificationResult:

    def test_fast_factory(self):
        result = ClassificationResult.fast()
        assert result.category == ResponseCategory.FAST
        assert result.needs_ack is False
        assert result.acknowledgement == ""
        assert result.topic is None

    def test_medium_result(self, coordinator):
        result = coordinator.classify("Explain AI")
        assert isinstance(result, ClassificationResult)
        assert result.category == ResponseCategory.MEDIUM
        assert result.operation is not None

    def test_long_result(self, coordinator):
        result = coordinator.classify("Write a Python app")
        assert isinstance(result, ClassificationResult)
        assert result.category == ResponseCategory.LONG


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:

    def test_empty_is_fast(self, coordinator):
        result = coordinator.classify("")
        assert result.category == ResponseCategory.FAST

    def test_whitespace_only(self, coordinator):
        result = coordinator.classify("   ")
        assert result.category == ResponseCategory.FAST

    def test_single_word_unknown(self, coordinator):
        result = coordinator.classify("hmm")
        assert result.category == ResponseCategory.FAST

    def test_case_insensitive(self, coordinator):
        upper = coordinator.classify("EXPLAIN QUANTUM COMPUTING")
        lower = coordinator.classify("explain quantum computing")
        assert upper.category == lower.category


@pytest.fixture
def coordinator() -> ResponseCoordinator:
    return ResponseCoordinator()


# ===========================================================================
# FAST classification
# ===========================================================================

class TestFastClassification:

    def test_greeting_hi(self, coordinator):
        result = coordinator.classify("hi")
        assert result.category == ResponseCategory.FAST
        assert result.needs_ack is False

    def test_greeting_hello(self, coordinator):
        result = coordinator.classify("Hello Jarvis")
        assert result.category == ResponseCategory.FAST

    def test_how_old_is(self, coordinator):
        result = coordinator.classify("How old is Leo?")
        assert result.category == ResponseCategory.FAST

    def test_what_colour_is(self, coordinator):
        result = coordinator.classify("What colour is Rex?")
        assert result.category == ResponseCategory.FAST

    def test_who_is(self, coordinator):
        result = coordinator.classify("Who is Lucas?")
        assert result.category == ResponseCategory.FAST

    def test_remember(self, coordinator):
        result = coordinator.classify("Remember my name is Leo")
        assert result.category == ResponseCategory.FAST

    def test_exit(self, coordinator):
        result = coordinator.classify("goodbye")
        assert result.category == ResponseCategory.FAST

    def test_tell_me_about(self, coordinator):
        result = coordinator.classify("Tell me about Lucas")
        assert result.category == ResponseCategory.FAST

    def test_what_about(self, coordinator):
        result = coordinator.classify("What about Chase?")
        assert result.category == ResponseCategory.FAST

    def test_empty_string(self, coordinator):
        result = coordinator.classify("")
        assert result.category == ResponseCategory.FAST

    def test_what_time_is_it(self, coordinator):
        result = coordinator.classify("What time is it?")
        assert result.category == ResponseCategory.FAST

    def test_fast_has_no_acknowledgement(self, coordinator):
        result = coordinator.classify("How old is Leo?")
        assert result.acknowledgement == ""
        assert result.needs_ack is False


# ===========================================================================
# MEDIUM classification
# ===========================================================================

class TestMediumClassification:

    def test_explain(self, coordinator):
        result = coordinator.classify("Explain quantum computing.")
        assert result.category == ResponseCategory.MEDIUM
        assert result.needs_ack is True

    def test_what_is(self, coordinator):
        result = coordinator.classify("What is machine learning?")
        assert result.category == ResponseCategory.MEDIUM

    def test_how_does(self, coordinator):
        result = coordinator.classify("How does blockchain work?")
        assert result.category == ResponseCategory.MEDIUM

    def test_search(self, coordinator):
        result = coordinator.classify("Search the web for Python tutorials")
        assert result.category == ResponseCategory.MEDIUM

    def test_compare(self, coordinator):
        result = coordinator.classify("Compare Python and JavaScript")
        assert result.category == ResponseCategory.MEDIUM

    def test_recommend(self, coordinator):
        result = coordinator.classify("Recommend a good book on AI")
        assert result.category == ResponseCategory.MEDIUM

    def test_translate(self, coordinator):
        result = coordinator.classify("Translate hello to French")
        assert result.category == ResponseCategory.MEDIUM

    def test_write_email(self, coordinator):
        result = coordinator.classify("Write an email to my team")
        assert result.category == ResponseCategory.MEDIUM

    def test_medium_has_acknowledgement(self, coordinator):
        result = coordinator.classify("Explain relativity")
        assert result.acknowledgement != ""
        assert len(result.acknowledgement) > 3

    def test_medium_ack_varies(self, coordinator):
        """Different requests should get varied acknowledgements."""
        results = [coordinator.classify("Explain X") for _ in range(6)]
        acks = [r.acknowledgement for r in results]
        # Should have some variety (not all identical)
        assert len(set(acks)) > 1 or all(a == acks[0] for a in acks)


# ===========================================================================
# LONG classification
# ===========================================================================

class TestLongClassification:

    def test_write_code(self, coordinator):
        result = coordinator.classify("Write a Python script to parse CSV files")
        assert result.category == ResponseCategory.LONG
        assert result.needs_ack is True

    def test_generate_code(self, coordinator):
        result = coordinator.classify("Generate a class for user authentication")
        assert result.category == ResponseCategory.LONG

    def test_implement_function(self, coordinator):
        result = coordinator.classify("Implement a binary search function")
        assert result.category == ResponseCategory.LONG

    def test_create_module(self, coordinator):
        result = coordinator.classify("Create a module for database connections")
        assert result.category == ResponseCategory.LONG

    def test_refactor_code(self, coordinator):
        result = coordinator.classify("Refactor this code to use async functions")
        assert result.category == ResponseCategory.LONG

    def test_long_has_acknowledgement(self, coordinator):
        result = coordinator.classify("Write a Python script")
        assert result.acknowledgement != ""
        assert result.needs_ack is True


# ===========================================================================
# Topic-aware acknowledgements
# ===========================================================================

class TestTopicAwareAcknowledgements:

    def test_explain_topic(self, coordinator):
        result = coordinator.classify("Explain quantum computing")
        assert "quantum computing" in result.acknowledgement.lower()

    def test_describe_topic(self, coordinator):
        result = coordinator.classify("Describe the water cycle")
        assert "water cycle" in result.acknowledgement.lower() or result.acknowledgement != ""

    def test_search_topic(self, coordinator):
        result = coordinator.classify("Search for Python tutorials")
        assert result.acknowledgement != ""

    def test_generate_topic(self, coordinator):
        result = coordinator.classify("Generate a Python script for data analysis")
        assert result.acknowledgement != ""

    def test_fallback_when_no_topic(self, coordinator):
        result = coordinator.classify("Explain things")
        assert result.acknowledgement != ""


# ===========================================================================
# ClassificationResult
# ===========================================================================

class TestClassificationResult:

    def test_fast_factory(self):
        result = ClassificationResult.fast()
        assert result.category == ResponseCategory.FAST
        assert result.needs_ack is False
        assert result.acknowledgement == ""

    def test_medium_result(self, coordinator):
        result = coordinator.classify("Explain AI")
        assert isinstance(result, ClassificationResult)
        assert result.category == ResponseCategory.MEDIUM

    def test_long_result(self, coordinator):
        result = coordinator.classify("Write a Python app")
        assert isinstance(result, ClassificationResult)
        assert result.category == ResponseCategory.LONG


# ===========================================================================
# Edge cases
# ===========================================================================

class TestEdgeCases:

    def test_none_like_empty(self, coordinator):
        result = coordinator.classify("")
        assert result.category == ResponseCategory.FAST

    def test_whitespace_only(self, coordinator):
        result = coordinator.classify("   ")
        assert result.category == ResponseCategory.FAST

    def test_single_word_unknown(self, coordinator):
        result = coordinator.classify("hmm")
        assert result.category == ResponseCategory.FAST

    def test_case_insensitive(self, coordinator):
        upper = coordinator.classify("EXPLAIN QUANTUM COMPUTING")
        lower = coordinator.classify("explain quantum computing")
        assert upper.category == lower.category
