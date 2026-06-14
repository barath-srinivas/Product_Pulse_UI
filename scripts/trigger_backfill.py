#!/usr/bin/env python3
"""Trigger dashboard backfill against a deployed pulse-api (Railway)."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request


def _request(base: str, path: str, *, method: str = "GET", body: dict | None = None) -> dict:
    url = f"{base.rstrip('/')}{path}"
    data = None
    headers = {"Accept": "application/json"}
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    with urllib.request.urlopen(req, timeout=120) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main() -> int:
    parser = argparse.ArgumentParser(description="Start pulse backfill on Railway pulse-api")
    parser.add_argument(
        "--api-url",
        default=os.getenv("PULSE_API_URL", "https://productpulseui-production.up.railway.app"),
        help="Railway pulse-api base URL",
    )
    parser.add_argument("--product", default="groww")
    parser.add_argument("--from-week", default="2026-W20")
    parser.add_argument("--to-week", default="2026-W24")
    parser.add_argument("--mock-llm", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--force-delivery", action="store_true")
    parser.add_argument("--poll", action="store_true", help="Poll job status until done")
    args = parser.parse_args()

    try:
        result = _request(
            args.api_url,
            "/api/runs/backfill",
            method="POST",
            body={
                "product": args.product,
                "from_week": args.from_week,
                "to_week": args.to_week,
                "mock_llm": args.mock_llm,
                "force": args.force,
                "force_delivery": args.force_delivery,
            },
        )
    except urllib.error.HTTPError as exc:
        print(exc.read().decode("utf-8"), file=sys.stderr)
        return 1

    job_id = result["job_id"]
    weeks = result.get("weeks", [])
    print(f"backfill_started job_id={job_id} weeks={','.join(weeks)}")

    if not args.poll:
        print(f"poll: GET {args.api_url.rstrip('/')}/api/runs/jobs/{job_id}")
        return 0

    while True:
        time.sleep(10)
        try:
            status = _request(args.api_url, f"/api/runs/jobs/{job_id}")
        except urllib.error.HTTPError as exc:
            print(exc.read().decode("utf-8"), file=sys.stderr)
            return 1
        current = status.get("backfill_current_week") or status.get("iso_week")
        print(
            f"status={status['status']} current={current} "
            f"completed={len(status.get('backfill_completed', []))}/{len(weeks)}"
        )
        if status["status"] in {"completed", "failed"}:
            if status.get("error"):
                print(f"error={status['error']}", file=sys.stderr)
            return 0 if status["status"] == "completed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
