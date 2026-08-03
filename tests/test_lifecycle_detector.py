"""
Tests — Engineering Lifecycle Detector
Genesis-034 Sprint-001
"""

import pytest
from core.engineering.lifecycle.detector import LifecycleDetector
from core.engineering.lifecycle.models import LifecycleCommandKind


class TestOpenGenesis:
    def setup_method(self):
        self.d = LifecycleDetector()

    def test_open_genesis_034(self):
        r = self.d.detect("Open Genesis-034.")
        assert r is not None
        assert r.kind == LifecycleCommandKind.OPEN_GENESIS
        assert r.genesis == "034"

    def test_open_genesis_no_dash(self):
        r = self.d.detect("Open Genesis 034")
        assert r is not None
        assert r.kind == LifecycleCommandKind.OPEN_GENESIS
        assert r.genesis == "034"

    def test_start_genesis(self):
        r = self.d.detect("Start Genesis-034")
        assert r is not None
        assert r.kind == LifecycleCommandKind.OPEN_GENESIS

    def test_begin_genesis(self):
        r = self.d.detect("Begin Genesis-034")
        assert r is not None
        assert r.kind == LifecycleCommandKind.OPEN_GENESIS

    def test_genesis_number_zero_padded(self):
        r = self.d.detect("Open Genesis-34")
        assert r is not None
        assert r.genesis == "034"

    def test_open_genesis_case_insensitive(self):
        r = self.d.detect("open genesis-034")
        assert r is not None
        assert r.kind == LifecycleCommandKind.OPEN_GENESIS


class TestCloseGenesis:
    def setup_method(self):
        self.d = LifecycleDetector()

    def test_close_genesis_034(self):
        r = self.d.detect("Close Genesis-034.")
        assert r is not None
        assert r.kind == LifecycleCommandKind.CLOSE_GENESIS
        assert r.genesis == "034"

    def test_complete_genesis(self):
        r = self.d.detect("Complete Genesis-034")
        assert r is not None
        assert r.kind == LifecycleCommandKind.CLOSE_GENESIS

    def test_finish_genesis(self):
        r = self.d.detect("Finish Genesis-034")
        assert r is not None
        assert r.kind == LifecycleCommandKind.CLOSE_GENESIS

    def test_end_genesis(self):
        r = self.d.detect("End Genesis-034")
        assert r is not None
        assert r.kind == LifecycleCommandKind.CLOSE_GENESIS

    def test_close_genesis_case_insensitive(self):
        r = self.d.detect("close genesis-034")
        assert r is not None
        assert r.kind == LifecycleCommandKind.CLOSE_GENESIS

    def test_close_takes_priority_over_open(self):
        """Close patterns checked before open patterns."""
        r = self.d.detect("Close Genesis-034")
        assert r.kind == LifecycleCommandKind.CLOSE_GENESIS


class TestNoDetection:
    def setup_method(self):
        self.d = LifecycleDetector()

    def test_unrelated_query(self):
        assert self.d.detect("What is the weather?") is None

    def test_review_request(self):
        assert self.d.detect("Review Genesis-033") is None

    def test_greeting(self):
        assert self.d.detect("Hello Jarvis") is None

    def test_empty(self):
        assert self.d.detect("") is None

    def test_genesis_without_number(self):
        assert self.d.detect("Open Genesis") is None

    def test_partial_match(self):
        assert self.d.detect("I was thinking about Genesis-034") is None
