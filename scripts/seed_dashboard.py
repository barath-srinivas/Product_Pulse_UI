#!/usr/bin/env python3
"""Copy multi-week dashboard fixtures into runs/ for local UI dev."""

from pulse.api.services.dashboard import seed_reports_from_fixtures

if __name__ == "__main__":
    seed_reports_from_fixtures()
    print("Seeded dashboard reports from tests/fixtures/dashboard_weeks/")
