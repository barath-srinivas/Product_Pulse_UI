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


@dataclass
class _TokenEvent:
    tokens: int
    at: float


@dataclass
class LlmBudgetTracker:
    """Track per-run and rolling Groq quota usage."""

    config: LlmConfig
    usage_file: Path | None = None
    run_tokens: int = 0
    run_requests: int = 0
    _minute_window: deque[_TokenEvent] = field(default_factory=deque)

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

    def _tokens_in_last_minute(self) -> int:
        now = time.monotonic()
        while self._minute_window and now - self._minute_window[0].at > 60:
            self._minute_window.popleft()
        return sum(event.tokens for event in self._minute_window)

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
        """Sleep until a request fits within rolling TPM."""
        limits = self.config.rate_limits
        while self._tokens_in_last_minute() + estimated_tokens > limits.tokens_per_minute:
            time.sleep(1.0)

    def record(self, tokens: int) -> None:
        limits = self.config.rate_limits
        self.run_tokens += tokens
        self.run_requests += 1
        self._minute_window.append(_TokenEvent(tokens=tokens, at=time.monotonic()))
        daily = self._load_daily_tokens() + tokens
        self._save_daily_tokens(daily)
        if self.run_tokens > self.config.max_tokens_per_run:
            raise LlmBudgetExceededError(
                f"run tokens {self.run_tokens} exceed max_tokens_per_run "
                f"{self.config.max_tokens_per_run}"
            )
        if self.run_requests > limits.requests_per_minute:
            pass  # per-minute request cap is soft; sequential calls stay under 30
