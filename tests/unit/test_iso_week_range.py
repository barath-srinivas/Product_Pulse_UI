"""Unit tests for ISO week range helper."""

import pytest

from pulse.config import iso_week_range, parse_iso_week


def test_iso_week_range_single_week() -> None:
    assert iso_week_range("2026-W24", "2026-W24") == ["2026-W24"]


def test_iso_week_range_multiple_weeks() -> None:
    weeks = iso_week_range("2026-W22", "2026-W24")
    assert weeks == ["2026-W22", "2026-W23", "2026-W24"]


def test_iso_week_range_rejects_inverted_range() -> None:
    with pytest.raises(ValueError, match="after end week"):
        iso_week_range("2026-W30", "2026-W20")


def test_parse_iso_week_valid() -> None:
    assert parse_iso_week("2026-W24") == (2026, 24)
