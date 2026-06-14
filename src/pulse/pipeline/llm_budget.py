"""Groq token and request budget tracking with TPM/TPD pacing."""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

from pulse.config import LlmConfig, get_project_root
from pulse.pipeline.exceptions import LlmBudgetExceededError

# Stay below Groq's published TPM to reduce 429s during burst clustering.
TPM_SAFETY_FACTOR = 0.85


@dataclass
class _TokenEvent:
    tokens: int
    at: float


@dataclass
class _RequestEvent:
    at: float


@dataclass
class LlmBudgetTracker:
    """Track per-run and rolling Groq quota usage."""

    config: LlmConfig
    usage_file: Path | None = None
    run_tokens: int = 0
    run_requests: int = 0
    _minute_window: deque[_TokenEvent] = field(default_factory=deque)
    _request_window: deque[_RequestEvent] = field(default_factory=deque)
    _last_request_at: float = 0.0

    def __post_init__(self) -> None:
        if self.usage_file is None:
            today = date.today().isoformat()
            path = get_project_root() / "data" / "groq_usage" / f"{today}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            self.usage_file = path

    def _load_daily_tokens(self) -> int:
        if self.usage_file is None or not self.usage_file.exists():
            return 0
        try:
            data = json.loads(self.usage_file.read_text(encoding="utf-8"))
            return int(data.get("tokens", 0))
        except (json.JSONDecodeError, OSError, TypeError, ValueError):
            return 0

    def _save_daily_tokens(self, total: int) -> None:
        if self.usage_file is None:
            return
        payload = {
            "date": date.today().isoformat(),
            "tokens": total,
            "updated_at": datetime.now().isoformat(),
        }
        self.usage_file.write_text(json.dumps(payload), encoding="utf-8")

    def _prune_windows(self, now: float) -> None:
        while self._minute_window and now - self._minute_window[0].at > 60:
            self._minute_window.popleft()
        while self._request_window and now - self._request_window[0].at > 60:
            self._request_window.popleft()

    def _tokens_in_last_minute(self) -> int:
        now = time.monotonic()
        self._prune_windows(now)
        return sum(event.tokens for event in self._minute_window)

    def _requests_in_last_minute(self) -> int:
        now = time.monotonic()
        self._prune_windows(now)
        return len(self._request_window)

    def preflight(self, estimated_tokens: int) -> None:
        """Abort before LLM if projected usage exceeds caps."""
        limits = self.config.rate_limits
        daily = self._load_daily_tokens()
        if self.run_tokens + estimated_tokens > self.config.max_tokens_per_run:
            raise LlmBudgetExceededError(
                f"projected run tokens {self.run_tokens + estimated_tokens} "
                f"exceed max_tokens_per_run {self.config.max_tokens_per_run}"
            )
        if daily + estimated_tokens > limits.tokens_per_day:
            raise LlmBudgetExceededError(
                f"projected daily tokens {daily + estimated_tokens} "
                f"exceed tokens_per_day {limits.tokens_per_day}"
            )
        if self.run_requests + 1 > limits.requests_per_day:
            raise LlmBudgetExceededError("daily Groq request limit exceeded")

    def wait_for_slot(self, estimated_tokens: int) -> None:
        """Sleep until the next request fits within rolling TPM/RPM and min gap."""
        limits = self.config.rate_limits
        tpm_cap = int(limits.tokens_per_minute * TPM_SAFETY_FACTOR)
        min_gap = self.config.min_seconds_between_requests

        if self._last_request_at:
            elapsed = time.monotonic() - self._last_request_at
            if elapsed < min_gap:
                time.sleep(min_gap - elapsed)

        while self._tokens_in_last_minute() + estimated_tokens > tpm_cap:
            time.sleep(2.0)

        while self._requests_in_last_minute() >= max(1, limits.requests_per_minute - 1):
            time.sleep(1.0)

    def record(self, tokens: int) -> None:
        limits = self.config.rate_limits
        now = time.monotonic()
        self.run_tokens += tokens
        self.run_requests += 1
        self._minute_window.append(_TokenEvent(tokens=tokens, at=now))
        self._request_window.append(_RequestEvent(at=now))
        self._last_request_at = now
        daily = self._load_daily_tokens() + tokens
        self._save_daily_tokens(daily)
        if self.run_tokens > self.config.max_tokens_per_run:
            raise LlmBudgetExceededError(
                f"run tokens {self.run_tokens} exceed max_tokens_per_run "
                f"{self.config.max_tokens_per_run}"
            )
        if self.run_requests > limits.requests_per_minute:
            pass  # per-minute request cap is soft; sequential calls stay under 30
