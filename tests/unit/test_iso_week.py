"""Unit tests for ISO week helpers (Asia/Kolkata)."""

from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

from pulse.config import (
    current_iso_week,
    iso_week_for_datetime,
    parse_iso_week,
)

IST = ZoneInfo("Asia/Kolkata")


def test_iso_week_for_datetime_monday_morning_ist() -> None:
    # 2026-06-08 is a Monday — ISO week 24 of 2026
    dt = datetime(2026, 6, 8, 8, 0, 0, tzinfo=IST)
    assert iso_week_for_datetime(dt) == "2026-W24"


def test_iso_week_sunday_late_night_ist() -> None:
    # 2026-06-07 23:59 IST is still Sunday, same ISO week as Monday 2026-06-08
    dt = datetime(2026, 6, 7, 23, 59, 0, tzinfo=IST)
    assert iso_week_for_datetime(dt) == "2026-W23"


def test_iso_week_monday_just_after_midnight_ist() -> None:
    dt = datetime(2026, 6, 8, 0, 1, 0, tzinfo=IST)
    assert iso_week_for_datetime(dt) == "2026-W24"


def test_iso_week_year_boundary() -> None:
    # 2025-12-29 is ISO week 1 of 2026 in ISO calendar
    dt = datetime(2025, 12, 29, 12, 0, 0, tzinfo=IST)
    assert iso_week_for_datetime(dt) == "2026-W01"


def test_current_iso_week_format() -> None:
    label = current_iso_week("Asia/Kolkata")
    assert "-W" in label
    year, week = parse_iso_week(label)
    assert 2000 <= year <= 2100
    assert 1 <= week <= 53


def test_parse_iso_week_valid() -> None:
    assert parse_iso_week("2026-W23") == (2026, 23)
    assert parse_iso_week("2026-W01") == (2026, 1)


def test_parse_iso_week_invalid() -> None:
    with pytest.raises(ValueError, match="invalid ISO week"):
        parse_iso_week("2026-23")
    with pytest.raises(ValueError, match="out of range"):
        parse_iso_week("2026-W54")
