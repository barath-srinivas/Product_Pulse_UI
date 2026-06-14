"""Load and aggregate dashboard data from report artifacts."""

from __future__ import annotations

import json
from pathlib import Path

from pulse.config import AppConfig, current_iso_week, load_config, normalize_iso_week
from pulse.ledger.store import LedgerStore, report_artifact_path
from pulse.pipeline.analytics import enrich_report
from pulse.pipeline.models import PulseReport

THEME_ICONS = ("🔥", "🎧", "📈", "⚡", "🛠️")


class DashboardError(Exception):
    """Raised when dashboard data cannot be loaded."""


def _theme_icon(rank: int) -> str:
    return THEME_ICONS[min(rank - 1, len(THEME_ICONS) - 1)]


def load_report(product_id: str, iso_week: str) -> PulseReport:
    path = report_artifact_path(product_id, iso_week)
    if not path.exists():
        raise DashboardError(f"no report for {product_id} week {iso_week}")
    report = PulseReport.model_validate_json(path.read_text(encoding="utf-8"))
    return enrich_report(report)


def load_report_optional(product_id: str, iso_week: str) -> PulseReport | None:
    try:
        return load_report(product_id, iso_week)
    except DashboardError:
        return None


def resolve_week(product_id: str, week: str | None, config: AppConfig) -> str:
    if week:
        return normalize_iso_week(week)
    return current_iso_week(config.pulse.timezone)


def list_available_weeks(product_id: str, ledger: LedgerStore | None = None) -> list[str]:
    store = ledger or LedgerStore()
    raw_weeks = list(store.list_completed_weeks(product_id))

    product_dir = report_artifact_path(product_id, "placeholder").parent.parent
    if product_dir.is_dir():
        for week_dir in product_dir.iterdir():
            if (week_dir / "report.json").exists():
                raw_weeks.append(week_dir.name)

    canonical: dict[str, str] = {}
    for label in raw_weeks:
        try:
            canonical[normalize_iso_week(label)] = normalize_iso_week(label)
        except ValueError:
            continue
    return sorted(canonical.values())


def seed_reports_from_fixtures() -> None:
    """Copy multi-week demo reports into runs/ for local dashboard dev."""
    fixture_dir = Path(__file__).resolve().parents[4] / "tests" / "fixtures" / "dashboard_weeks"
    if not fixture_dir.is_dir():
        return
    for path in sorted(fixture_dir.glob("*.json")):
        report = PulseReport.model_validate_json(path.read_text(encoding="utf-8"))
        dest = report_artifact_path(report.product_id, report.iso_week)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(report.model_dump_json(indent=2), encoding="utf-8")
