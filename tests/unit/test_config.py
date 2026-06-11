"""Unit tests for configuration loading."""

from pathlib import Path

import pytest
import yaml

from pulse.config import (
    GROWW_PLAY_PACKAGE,
    GROWW_PRODUCT_ID,
    load_config,
    load_products,
    load_pulse_config,
    resolve_config_dir,
)


def test_resolve_config_dir_default(project_root: Path) -> None:
    assert resolve_config_dir() == project_root / "config"


def test_load_config_from_example(config_dir: Path) -> None:
    config = load_config(config_dir)
    assert GROWW_PRODUCT_ID in config.products
    groww = config.products[GROWW_PRODUCT_ID]
    assert groww.display_name == "Groww"
    assert groww.google_play_package == GROWW_PLAY_PACKAGE
    assert config.pulse.timezone == "Asia/Kolkata"
    assert config.pulse.delivery.email_mode == "draft"
    assert config.pulse.ingest.min_words == 8
    assert config.pulse.ingest.english_only is True
    assert config.pulse.ingest.reject_emojis is True
    assert config.mcp_delivery is not None
    delivery = config.mcp_delivery.google_mcp_delivery
    assert delivery.base_url == "https://web-production-facdf.up.railway.app"
    assert delivery.endpoints.append_to_doc == "/append_to_doc"
    assert delivery.endpoints.create_email_draft == "/create_email_draft"


def test_load_pulse_config(config_dir: Path) -> None:
    pulse = load_pulse_config(config_dir)
    assert pulse.review_window_weeks == 10
    assert pulse.min_reviews_required == 50
    assert pulse.clustering.top_k_themes == 5
    assert pulse.llm.provider == "groq"
    assert pulse.llm.model == "llama-3.3-70b-versatile"
    assert pulse.llm.rate_limits.tokens_per_day == 100000
    assert pulse.embeddings.provider == "bge"
    assert pulse.embeddings.model == "BAAI/bge-small-en-v1.5"


def test_load_config_rejects_wrong_groww_package(tmp_path: Path, config_dir: Path) -> None:
    bad_products = {
        "products": {
            "groww": {
                "display_name": "Groww",
                "google_play_package": "com.wrong.package",
                "google_doc": {"title": "T", "document_id": "id"},
                "stakeholders": {"to": ["a@b.com"], "cc": []},
            }
        }
    }
    (tmp_path / "products.yaml").write_text(yaml.dump(bad_products), encoding="utf-8")
    (tmp_path / "pulse.yaml").write_text(
        (config_dir / "pulse.yaml").read_text(encoding="utf-8"),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="google_play_package"):
        load_config(tmp_path, include_mcp=False)


def test_get_product_unknown_id(config_dir: Path) -> None:
    config = load_config(config_dir)
    with pytest.raises(KeyError, match="unknown product_id"):
        config.get_product("kuvera")


def test_missing_products_file(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_products(tmp_path)


def test_app_config_requires_groww(tmp_path: Path) -> None:
    products = {
        "products": {
            "other": {
                "display_name": "Other",
                "google_play_package": "com.other.app",
                "google_doc": {"title": "T", "document_id": "id"},
                "stakeholders": {"to": ["a@b.com"], "cc": []},
            }
        }
    }
    (tmp_path / "products.yaml").write_text(yaml.dump(products), encoding="utf-8")
    (tmp_path / "pulse.yaml").write_text(
        (Path(__file__).parent.parent.parent / "config" / "pulse.yaml").read_text(
            encoding="utf-8"
        ),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="missing required product"):
        load_config(tmp_path, include_mcp=False)
