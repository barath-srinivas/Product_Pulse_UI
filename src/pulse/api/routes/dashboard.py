"""Dashboard read endpoints."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from pulse.api.services import analytics
from pulse.api.services.dashboard import DashboardError, list_available_weeks, resolve_week, seed_reports_from_fixtures
from pulse.config import load_config

router = APIRouter(prefix="/api/dashboard", tags=["dashboard"])


@router.get("/weeks")
def get_weeks(product: str = Query(default="groww")) -> dict:
    return {"product_id": product, "weeks": list_available_weeks(product)}


@router.post("/seed-demo")
def seed_demo() -> dict:
    """Load multi-week fixture reports into runs/ (local dev only)."""
    seed_reports_from_fixtures()
    return {"status": "ok", "message": "demo reports seeded from tests/fixtures/dashboard_weeks"}


@router.get("/overview")
def overview(product: str = Query(default="groww"), week: str | None = None):
    config = load_config(include_mcp=False)
    iso_week = resolve_week(product, week, config)
    try:
        return analytics.build_overview(config, product, iso_week)
    except DashboardError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/themes")
def themes(product: str = Query(default="groww"), week: str | None = None):
    config = load_config(include_mcp=False)
    iso_week = resolve_week(product, week, config)
    try:
        return analytics.build_top_themes(product, iso_week)
    except DashboardError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/trends")
def trends(product: str = Query(default="groww"), weeks: int = Query(default=12, ge=1, le=52)):
    try:
        return analytics.build_trends(product, weeks=weeks)
    except DashboardError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/customer-voice")
def customer_voice(product: str = Query(default="groww"), week: str | None = None):
    config = load_config(include_mcp=False)
    iso_week = resolve_week(product, week, config)
    try:
        return analytics.build_customer_voice(product, iso_week)
    except DashboardError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
