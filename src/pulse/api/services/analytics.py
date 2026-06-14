"""Transform PulseReport data into dashboard API responses."""

from __future__ import annotations

from pulse.api.schemas import (
    CustomerVoiceResponse,
    EmergingIssue,
    OverviewResponse,
    ThemeItem,
    TopThemesResponse,
    TrendPoint,
    TrendsResponse,
)
from pulse.api.services.dashboard import _theme_icon, list_available_weeks, load_report, load_report_optional
from pulse.config import AppConfig, parse_iso_week
from pulse.ledger.store import LedgerStore


def _theme_items(report) -> list[ThemeItem]:
    return [
        ThemeItem(
            theme_name=t.theme_name,
            review_share_pct=t.review_share_pct,
            review_count=t.review_count,
            rank=t.rank,
            icon=_theme_icon(t.rank),
        )
        for t in sorted(report.themes, key=lambda x: x.rank)
    ]


def build_overview(config: AppConfig, product_id: str, iso_week: str) -> OverviewResponse:
    product = config.get_product(product_id)
    report = load_report(product_id, iso_week)
    return OverviewResponse(
        product_id=product_id,
        display_name=product.display_name,
        iso_week=iso_week,
        review_count=report.review_count,
        theme_count=len(report.themes),
        avg_rating=report.avg_rating,
    )


def build_top_themes(product_id: str, iso_week: str) -> TopThemesResponse:
    report = load_report(product_id, iso_week)
    return TopThemesResponse(
        product_id=product_id,
        iso_week=iso_week,
        themes=_theme_items(report),
    )


def build_trends(product_id: str, *, weeks: int = 12) -> TrendsResponse:
    available = list_available_weeks(product_id)[-weeks:]
    series: list[TrendPoint] = []
    for iso_week in available:
        report = load_report_optional(product_id, iso_week)
        if report is None:
            continue
        for theme in report.themes:
            series.append(
                TrendPoint(
                    iso_week=iso_week,
                    theme_name=theme.theme_name,
                    review_share_pct=theme.review_share_pct,
                )
            )
    return TrendsResponse(product_id=product_id, weeks=available, series=series)


def _previous_week(iso_week: str) -> str | None:
    year, week = parse_iso_week(iso_week)
    if week > 1:
        return f"{year}-W{week - 1:02d}"
    return f"{year - 1}-W52"


def build_customer_voice(product_id: str, iso_week: str) -> CustomerVoiceResponse:
    report = load_report(product_id, iso_week)
    sentiment = report.sentiment
    positive = sentiment.positive_pct if sentiment else 0.0
    negative = sentiment.negative_pct if sentiment else 0.0
    neutral = sentiment.neutral_pct if sentiment else 0.0

    emerging: list[EmergingIssue] = []
    prev_week = _previous_week(iso_week)
    if prev_week:
        prev_report = load_report_optional(product_id, prev_week)
        if prev_report:
            prev_map = {t.theme_name: t.review_share_pct for t in prev_report.themes}
            for theme in report.themes:
                prev_share = prev_map.get(theme.theme_name)
                if prev_share is not None and prev_share > 0:
                    change = round((theme.review_share_pct - prev_share) / prev_share * 100, 1)
                    emerging.append(EmergingIssue(theme_name=theme.theme_name, change_pct=change))
            emerging.sort(key=lambda e: e.change_pct, reverse=True)

    return CustomerVoiceResponse(
        product_id=product_id,
        iso_week=iso_week,
        review_count=report.review_count,
        positive_pct=positive,
        negative_pct=negative,
        neutral_pct=neutral,
        top_themes=_theme_items(report)[:5],
        emerging_issues=emerging[:5],
    )
