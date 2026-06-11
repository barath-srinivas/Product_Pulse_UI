"""Shared pytest fixtures."""

from pathlib import Path

import pytest

from pulse.config import PulseConfig, load_pulse_config


@pytest.fixture
def project_root() -> Path:
    return Path(__file__).resolve().parent.parent


@pytest.fixture
def config_dir(project_root: Path) -> Path:
    return project_root / "config"


@pytest.fixture
def pulse_config(config_dir: Path) -> PulseConfig:
    return load_pulse_config(config_dir)


@pytest.fixture
def pulse_config_fast(pulse_config: PulseConfig) -> PulseConfig:
    """Pulse config with TF-IDF embeddings for fast pipeline unit tests."""
    pulse_config.embeddings.provider = "tfidf"
    return pulse_config
