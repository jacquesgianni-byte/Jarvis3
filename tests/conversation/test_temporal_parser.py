"""
Tests for Genesis-047 Sprint-003: TimeOfDaySlot temporal granularity.

Verified mappings (per approved architecture):
    this morning   -> MORNING
    this afternoon -> AFTERNOON
    this evening   -> EVENING
    tonight        -> NIGHT
    last night     -> NIGHT
    today (alone)  -> UNSPECIFIED  (no sub-day slot inferred from clock)
"""
from __future__ import annotations

from datetime import date

import pytest

from core.conversation.temporal_parser import (
    TemporalContext,
    TemporalParser,
    TemporalTense,
    TemporalType,
    TimeOfDaySlot,
)


# ── TimeOfDaySlot enum ────────────────────────────────────────────────────────

class TestTimeOfDaySlotEnum:
    def test_all_members_exist(self):
        names = {m.name for m in TimeOfDaySlot}
        assert names == {"MORNING", "AFTERNOON", "EVENING", "NIGHT", "UNSPECIFIED"}

    def test_values(self):
        assert TimeOfDaySlot.MORNING.value     == "morning"
        assert TimeOfDaySlot.AFTERNOON.value   == "afternoon"
        assert TimeOfDaySlot.EVENING.value     == "evening"
        assert TimeOfDaySlot.NIGHT.value       == "night"
        assert TimeOfDaySlot.UNSPECIFIED.value == "unspecified"

    def test_default_is_unspecified(self):
        assert TimeOfDaySlot.UNSPECIFIED.value == "unspecified"


# ── TemporalContext default and backwards compat ──────────────────────────────

REF = date(2026, 8, 14)  # A Friday


class TestTemporalContextDefault:
    def test_time_of_day_slot_defaults_to_unspecified(self):
        """Existing construction sites that omit time_of_day_slot get UNSPECIFIED."""
        ctx = TemporalContext(
            expression="last week",
            temporal_type=TemporalType.PAST_RELATIVE,
            tense=TemporalTense.PAST,
            resolved_date=date(2026, 8, 7),
            offset_days=-7,
            reference_date=REF,
        )
        assert ctx.time_of_day_slot is TimeOfDaySlot.UNSPECIFIED

    def test_explicit_slot_preserved(self):
        ctx = TemporalContext(
            expression="this morning",
            temporal_type=TemporalType.PRESENT,
            tense=TemporalTense.PRESENT,
            resolved_date=REF,
            offset_days=0,
            reference_date=REF,
            time_of_day_slot=TimeOfDaySlot.MORNING,
        )
        assert ctx.time_of_day_slot is TimeOfDaySlot.MORNING

    def test_none_sentinel_becomes_unspecified(self):
        """Passing None explicitly also resolves to UNSPECIFIED via __post_init__."""
        ctx = TemporalContext(
            expression="yesterday",
            temporal_type=TemporalType.PAST_RELATIVE,
            tense=TemporalTense.PAST,
            resolved_date=date(2026, 8, 13),
            offset_days=-1,
            reference_date=REF,
            time_of_day_slot=None,
        )
        assert ctx.time_of_day_slot is TimeOfDaySlot.UNSPECIFIED


# ── TemporalParser slot assignment ────────────────────────────────────────────

class TestTemporalParserSlotAssignment:
    """
    Approved mappings from architecture review:
        this morning   -> MORNING
        this afternoon -> AFTERNOON
        this evening   -> EVENING
        tonight        -> NIGHT
        last night     -> NIGHT
        today (alone)  -> UNSPECIFIED
    """

    def setup_method(self):
        self.parser = TemporalParser()
        self.ref = REF

    def _parse(self, text: str) -> TemporalContext:
        ctx = self.parser.parse(text, self.ref)
        assert ctx is not None, f"No temporal context parsed from: {text!r}"
        return ctx

    def test_this_morning_maps_to_morning(self):
        ctx = self._parse("I finished it this morning")
        assert ctx.time_of_day_slot is TimeOfDaySlot.MORNING

    def test_this_afternoon_maps_to_afternoon(self):
        ctx = self._parse("We met this afternoon")
        assert ctx.time_of_day_slot is TimeOfDaySlot.AFTERNOON

    def test_this_evening_maps_to_evening(self):
        ctx = self._parse("I'll do it this evening")
        assert ctx.time_of_day_slot is TimeOfDaySlot.EVENING

    def test_tonight_maps_to_night(self):
        ctx = self._parse("Let's finish it tonight")
        assert ctx.time_of_day_slot is TimeOfDaySlot.NIGHT

    def test_last_night_maps_to_night(self):
        ctx = self._parse("I deployed last night")
        assert ctx.time_of_day_slot is TimeOfDaySlot.NIGHT

    def test_today_alone_maps_to_unspecified(self):
        """
        Critical: 'today' without a sub-day phrase must NOT infer a slot.
        Time-of-day is NEVER inferred from the current clock.
        """
        ctx = self._parse("I did that today")
        assert ctx.time_of_day_slot is TimeOfDaySlot.UNSPECIFIED

    def test_earlier_today_maps_to_unspecified(self):
        """'earlier today' names no specific part of the day."""
        ctx = self._parse("I saw that earlier today")
        assert ctx.time_of_day_slot is TimeOfDaySlot.UNSPECIFIED

    def test_yesterday_maps_to_unspecified(self):
        """Plain past-day expressions have no sub-day slot."""
        ctx = self._parse("I did it yesterday")
        assert ctx.time_of_day_slot is TimeOfDaySlot.UNSPECIFIED

    def test_last_week_maps_to_unspecified(self):
        ctx = self._parse("We finished it last week")
        assert ctx.time_of_day_slot is TimeOfDaySlot.UNSPECIFIED

    def test_last_night_tense_is_past(self):
        ctx = self._parse("I deployed last night")
        assert ctx.tense is TemporalTense.PAST

    def test_this_morning_tense_is_present(self):
        ctx = self._parse("I finished it this morning")
        assert ctx.tense is TemporalTense.PRESENT

    def test_this_morning_resolved_date_is_today(self):
        ctx = self._parse("I finished it this morning")
        assert ctx.resolved_date == self.ref

    def test_last_night_resolved_date_is_yesterday(self):
        ctx = self._parse("I deployed last night")
        assert ctx.resolved_date == date(2026, 8, 13)


# ── to_metadata() serialisation ───────────────────────────────────────────────

class TestTemporalContextToMetadata:
    def test_morning_slot_in_metadata(self):
        ctx = TemporalContext(
            expression="this morning",
            temporal_type=TemporalType.PRESENT,
            tense=TemporalTense.PRESENT,
            resolved_date=REF,
            offset_days=0,
            reference_date=REF,
            time_of_day_slot=TimeOfDaySlot.MORNING,
        )
        meta = ctx.to_metadata()
        assert "time_of_day_slot" in meta
        assert meta["time_of_day_slot"] == "morning"

    def test_unspecified_slot_in_metadata(self):
        ctx = TemporalContext(
            expression="yesterday",
            temporal_type=TemporalType.PAST_RELATIVE,
            tense=TemporalTense.PAST,
            resolved_date=date(2026, 8, 13),
            offset_days=-1,
            reference_date=REF,
        )
        meta = ctx.to_metadata()
        assert meta["time_of_day_slot"] == "unspecified"

    def test_all_slot_values_serialise(self):
        for slot in TimeOfDaySlot:
            ctx = TemporalContext(
                expression="test",
                temporal_type=TemporalType.PRESENT,
                tense=TemporalTense.PRESENT,
                resolved_date=REF,
                offset_days=0,
                reference_date=REF,
                time_of_day_slot=slot,
            )
            meta = ctx.to_metadata()
            assert meta["time_of_day_slot"] == slot.value

    def test_metadata_still_contains_existing_keys(self):
        """Ensure Sprint-003 change doesn't remove existing metadata keys."""
        ctx = TemporalContext(
            expression="this morning",
            temporal_type=TemporalType.PRESENT,
            tense=TemporalTense.PRESENT,
            resolved_date=REF,
            offset_days=0,
            reference_date=REF,
            time_of_day_slot=TimeOfDaySlot.MORNING,
        )
        meta = ctx.to_metadata()
        assert "temporal_expression" in meta
        assert "temporal_type" in meta
        assert "temporal_tense" in meta
        assert "resolved_date" in meta


# ── TemporalRecallEngine._format_answer() ─────────────────────────────────────

class TestTemporalRecallFormatting:
    def setup_method(self):
        from core.conversation.temporal_recall_engine import TemporalRecallEngine
        self.engine = TemporalRecallEngine()

    def test_morning_slot_produces_natural_phrasing(self):
        result = self.engine._format_answer(
            memory_value="met the client",
            resolved_date="2026-08-14",
            original_expression="this morning",
            time_of_day_slot="morning",
        )
        assert "morning" in result
        assert "Friday" in result
        # Should NOT have the parenthetical form
        assert "(this morning)" not in result

    def test_afternoon_slot_produces_natural_phrasing(self):
        result = self.engine._format_answer(
            memory_value="had the call",
            resolved_date="2026-08-14",
            original_expression="this afternoon",
            time_of_day_slot="afternoon",
        )
        assert "afternoon" in result
        assert "(this afternoon)" not in result

    def test_evening_slot_produces_natural_phrasing(self):
        result = self.engine._format_answer(
            memory_value="finished the sprint",
            resolved_date="2026-08-14",
            original_expression="this evening",
            time_of_day_slot="evening",
        )
        assert "evening" in result

    def test_night_slot_produces_natural_phrasing(self):
        result = self.engine._format_answer(
            memory_value="deployed",
            resolved_date="2026-08-13",
            original_expression="last night",
            time_of_day_slot="night",
        )
        assert "night" in result
        assert "(last night)" not in result

    def test_unspecified_slot_falls_back_to_expression(self):
        """Genesis-052 Sprint-003: when slot is unspecified, event content is used.
        Old behaviour: date-only with (last Monday) parenthetical.
        New behaviour: "On Monday, 27 July 2026, you started job."
        """
        result = self.engine._format_answer(
            memory_value="started job",
            resolved_date="2026-07-27",
            original_expression="last Monday",
            time_of_day_slot="unspecified",
        )
        assert "Monday" in result
        assert "27 July 2026" in result
        assert "started job" in result

    def test_unspecified_no_expression_plain_date(self):
        """Genesis-052 Sprint-003: no slot, no expression -> event content with date.
        Old behaviour: "That was on Monday, 27 July 2026."
        New behaviour: "On Monday, 27 July 2026, you started job."
        """
        result = self.engine._format_answer(
            memory_value="started job",
            resolved_date="2026-07-27",
            original_expression=None,
            time_of_day_slot="unspecified",
        )
        assert "Monday" in result
        assert "27 July 2026" in result
        assert "started job" in result
        assert "(" not in result

    def test_backwards_compat_no_slot_arg(self):
        """Calling _format_answer without time_of_day_slot still works."""
        result = self.engine._format_answer(
            memory_value="started job",
            resolved_date="2026-07-27",
            original_expression="last Monday",
        )
        assert "Monday" in result
