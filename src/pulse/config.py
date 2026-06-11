"""Configuration loading and timezone helpers for the pulse pipeline."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Literal
from zoneinfo import ZoneInfo

import yaml
from pydantic import BaseModel, Field, field_validator, model_validator

GROWW_PRODUCT_ID = "groww"
GROWW_PLAY_PACKAGE = "com.nextbillion.groww"
DEFAULT_TIMEZONE = "Asia/Kolkata"
DEFAULT_GROQ_MODEL = "llama-3.3-70b-versatile"
DEFAULT_BGE_MODEL = "BAAI/bge-small-en-v1.5"


class GoogleDocConfig(BaseModel):
    title: str
    document_id: str


class StakeholdersConfig(BaseModel):
    to: list[str] = Field(default_factory=list)
    cc: list[str] = Field(default_factory=list)

    @field_validator("to", "cc")
    @classmethod
    def validate_emails_not_empty_strings(cls, values: list[str]) -> list[str]:
        for email in values:
            if not email or not email.strip():
                raise ValueError("email entries must be non-empty strings")
        return values


class ProductConfig(BaseModel):
    display_name: str
    google_play_package: str
    google_doc: GoogleDocConfig
    stakeholders: StakeholdersConfig

    @field_validator("google_play_package")
    @classmethod
    def validate_play_package(cls, value: str) -> str:
        if not value or "." not in value:
            raise ValueError("google_play_package must be a valid package id")
        return value


class ClusteringConfig(BaseModel):
    umap_n_components: int = 5
    umap_n_neighbors: int = 15
    umap_random_state: int = 42
    hdbscan_min_cluster_size: int = 8
    hdbscan_min_samples: int = 3
    top_k_themes: int = 5


class LlmRateLimitsConfig(BaseModel):
    requests_per_minute: int = 30
    requests_per_day: int = 1000
    tokens_per_minute: int = 12000
    tokens_per_day: int = 100000


class LlmConfig(BaseModel):
    provider: Literal["groq"] = "groq"
    model: str = DEFAULT_GROQ_MODEL
    temperature: float = 0.2
    max_tokens_per_request: int = 4096
    max_tokens_per_run: int = 20000
    rate_limits: LlmRateLimitsConfig = Field(default_factory=LlmRateLimitsConfig)


class EmbeddingsConfig(BaseModel):
    provider: Literal["tfidf", "bge"] = "bge"
    model: str = DEFAULT_BGE_MODEL
    batch_size: int = 64


class SafetyConfig(BaseModel):
    max_quote_length: int = 280
    pii_scrub: bool = True


class IngestConfig(BaseModel):
    min_words: int = Field(default=8, ge=1)
    english_only: bool = True
    reject_emojis: bool = True


class DeliveryConfig(BaseModel):
    email_mode: Literal["draft", "send"] = "draft"


class ScheduleConfig(BaseModel):
    cron: str = "0 8 * * 1"


class PulseConfig(BaseModel):
    review_window_weeks: int = Field(ge=1, le=52)
    min_reviews_required: int = Field(ge=1)
    ingest: IngestConfig = Field(default_factory=IngestConfig)
    clustering: ClusteringConfig
    embeddings: EmbeddingsConfig = Field(default_factory=EmbeddingsConfig)
    llm: LlmConfig
    safety: SafetyConfig
    delivery: DeliveryConfig
    timezone: str = DEFAULT_TIMEZONE
    schedule: ScheduleConfig

    @field_validator("timezone")
    @classmethod
    def validate_timezone(cls, value: str) -> str:
        try:
            ZoneInfo(value)
        except Exception as exc:
            raise ValueError(f"invalid timezone: {value}") from exc
        return value


class GoogleMcpEndpointsConfig(BaseModel):
    health: str = "/health"
    append_to_doc: str = Field(default="/append_to_doc", alias="appendToDoc")
    create_email_draft: str = Field(default="/create_email_draft", alias="createEmailDraft")

    model_config = {"populate_by_name": True}


class GoogleMcpDeliveryConfig(BaseModel):
    base_url: str = Field(alias="baseUrl")
    api_key_env: str = Field(default="GOOGLE_MCP_API_KEY", alias="apiKeyEnv")
    endpoints: GoogleMcpEndpointsConfig = Field(default_factory=GoogleMcpEndpointsConfig)

    model_config = {"populate_by_name": True}

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        if not value.startswith("https://"):
            raise ValueError("googleMcpDelivery.baseUrl must use https")
        return value.rstrip("/")


class McpDeliveryConfig(BaseModel):
    google_mcp_delivery: GoogleMcpDeliveryConfig = Field(alias="googleMcpDelivery")

    model_config = {"populate_by_name": True}


class AppConfig(BaseModel):
    products: dict[str, ProductConfig]
    pulse: PulseConfig
    mcp_delivery: McpDeliveryConfig | None = None

    @model_validator(mode="after")
    def validate_groww_scope(self) -> AppConfig:
        if GROWW_PRODUCT_ID not in self.products:
            raise ValueError(f"missing required product: {GROWW_PRODUCT_ID}")
        groww = self.products[GROWW_PRODUCT_ID]
        if groww.google_play_package != GROWW_PLAY_PACKAGE:
            raise ValueError(
                f"groww google_play_package must be {GROWW_PLAY_PACKAGE!r}, "
                f"got {groww.google_play_package!r}"
            )
        return self

    def get_product(self, product_id: str) -> ProductConfig:
        if product_id not in self.products:
            raise KeyError(
                f"unknown product_id: {product_id!r}. "
                f"Available: {sorted(self.products)}"
            )
        return self.products[product_id]


def get_project_root() -> Path:
    """Return repository root (parent of src/)."""
    return Path(__file__).resolve().parent.parent.parent


def resolve_config_dir(config_dir: Path | None = None) -> Path:
    if config_dir is not None:
        return config_dir.expanduser().resolve()
    env_dir = os.getenv("PULSE_CONFIG_DIR")
    if env_dir:
        return Path(env_dir).expanduser().resolve()
    return get_project_root() / "config"


def _load_yaml(path: Path) -> dict:
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        data = yaml.safe_load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"expected mapping in {path}")
    return data


def load_products(config_dir: Path) -> dict[str, ProductConfig]:
    path = config_dir / "products.yaml"
    if not path.exists():
        path = config_dir / "products.example.yaml"
    raw = _load_yaml(path)
    products_raw = raw.get("products", {})
    return {pid: ProductConfig.model_validate(cfg) for pid, cfg in products_raw.items()}


def load_pulse_config(config_dir: Path) -> PulseConfig:
    raw = _load_yaml(config_dir / "pulse.yaml")
    return PulseConfig.model_validate(raw)


def load_mcp_delivery(config_dir: Path) -> McpDeliveryConfig:
    path = config_dir / "mcp-servers.json"
    if not path.exists():
        raise FileNotFoundError(f"config file not found: {path}")
    with path.open(encoding="utf-8") as handle:
        raw = json.load(handle)
    return McpDeliveryConfig.model_validate(raw)


def load_config(config_dir: Path | None = None, *, include_mcp: bool = True) -> AppConfig:
    """Load and validate all configuration from the config directory."""
    resolved = resolve_config_dir(config_dir)
    products = load_products(resolved)
    pulse = load_pulse_config(resolved)
    mcp = load_mcp_delivery(resolved) if include_mcp else None
    return AppConfig(products=products, pulse=pulse, mcp_delivery=mcp)


def iso_week_for_datetime(dt: datetime, timezone: str = DEFAULT_TIMEZONE) -> str:
    """Return ISO week label YYYY-Www for a timezone-aware or naive datetime."""
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo(timezone))
    else:
        dt = dt.astimezone(ZoneInfo(timezone))
    iso = dt.isocalendar()
    return f"{iso.year}-W{iso.week:02d}"


def current_iso_week(timezone: str = DEFAULT_TIMEZONE) -> str:
    """Return the current ISO week label in the given timezone."""
    now = datetime.now(ZoneInfo(timezone))
    return iso_week_for_datetime(now, timezone)


def format_iso_week(iso_year: int, iso_week: int) -> str:
    """Format ISO calendar year and week number as YYYY-Www."""
    return f"{iso_year}-W{iso_week:02d}"


def iso_week_range(start: str, end: str) -> list[str]:
    """Return inclusive ISO week labels from start through end."""
    from datetime import date, timedelta

    start_year, start_week = parse_iso_week(start)
    end_year, end_week = parse_iso_week(end)
    start_date = date.fromisocalendar(start_year, start_week, 1)
    end_date = date.fromisocalendar(end_year, end_week, 1)
    if start_date > end_date:
        raise ValueError(f"start week {start!r} is after end week {end!r}")

    weeks: list[str] = []
    current = start_date
    while current <= end_date:
        iso = current.isocalendar()
        label = format_iso_week(iso.year, iso.week)
        if not weeks or weeks[-1] != label:
            weeks.append(label)
        current += timedelta(days=7)
    return weeks


def parse_iso_week(iso_week: str) -> tuple[int, int]:
    """Parse YYYY-Www into (iso_year, iso_week_number)."""
    if len(iso_week) < 8 or "-W" not in iso_week:
        raise ValueError(f"invalid ISO week format: {iso_week!r}; expected YYYY-Www")
    year_str, week_str = iso_week.split("-W", maxsplit=1)
    try:
        year = int(year_str)
        week = int(week_str)
    except ValueError as exc:
        raise ValueError(f"invalid ISO week format: {iso_week!r}") from exc
    if week < 1 or week > 53:
        raise ValueError(f"ISO week number out of range: {week}")
    return year, week
