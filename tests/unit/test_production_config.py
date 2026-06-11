"""Unit tests for Phase 9 production config and scheduler settings."""

from pathlib import Path

import yaml

from pulse.config import GROWW_PRODUCT_ID, ProductConfig, load_pulse_config


def test_production_example_yaml_loads(project_root: Path) -> None:
    path = project_root / "config" / "products.production.example.yaml"
    assert path.exists()
    with path.open(encoding="utf-8") as handle:
        raw = yaml.safe_load(handle)
    products = {
        pid: ProductConfig.model_validate(cfg) for pid, cfg in raw["products"].items()
    }
    groww = products[GROWW_PRODUCT_ID]
    assert groww.google_play_package == "com.nextbillion.groww"
    assert "Staging" not in groww.google_doc.title
    assert groww.google_doc.document_id
    assert len(groww.stakeholders.to) >= 1
    assert "example.com" not in groww.stakeholders.to[0]


def test_pulse_schedule_monday_ist(config_dir: Path) -> None:
    pulse = load_pulse_config(config_dir)
    assert pulse.schedule.cron == "0 8 * * 1"
    assert pulse.timezone == "Asia/Kolkata"
    assert pulse.delivery.email_mode == "draft"


def test_scheduled_run_scripts_exist(project_root: Path) -> None:
    assert (project_root / "scripts" / "scheduled_run.sh").exists()
    assert (project_root / "scripts" / "scheduled_run.ps1").exists()
