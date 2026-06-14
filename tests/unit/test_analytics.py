"""Dashboard analytics unit tests."""

import json
from pathlib import Path

from pulse.api.services.analytics import build_customer_voice, build_overview, build_trends
from pulse.api.services.dashboard import seed_reports_from_fixtures
from pulse.config import load_config


def test_dashboard_analytics_from_fixtures(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("pulse.ledger.store.get_runs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "pulse.api.services.dashboard.report_artifact_path",
        lambda product_id, iso_week: tmp_path / product_id / iso_week / "report.json",
    )
    fixture_dir = Path(__file__).parent.parent / "fixtures" / "dashboard_weeks"
    for path in fixture_dir.glob("*.json"):
        report = json.loads(path.read_text(encoding="utf-8"))
        dest = tmp_path / report["product_id"] / report["iso_week"] / "report.json"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(report), encoding="utf-8")

    config = load_config(include_mcp=False)
    overview = build_overview(config, "groww", "2026-W24")
    assert overview.review_count == 1247
    assert overview.theme_count == 5
    assert overview.avg_rating == 3.9

    trends = build_trends("groww", weeks=12)
    assert len(trends.weeks) == 5

    voice = build_customer_voice("groww", "2026-W24")
    assert voice.positive_pct == 67.0
    assert voice.emerging_issues


def test_seed_dashboard_script(tmp_path, monkeypatch) -> None:
    monkeypatch.setattr("pulse.ledger.store.get_runs_dir", lambda: tmp_path)
    monkeypatch.setattr(
        "pulse.api.services.dashboard.report_artifact_path",
        lambda product_id, iso_week: tmp_path / product_id / iso_week / "report.json",
    )
    seed_reports_from_fixtures()
    assert (tmp_path / "groww" / "2026-W24" / "report.json").exists()
