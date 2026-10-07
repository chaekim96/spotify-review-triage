"""Rates, cost arithmetic, the shared spend ledger and the shared rate limiter.

One ledger and one limiter are shared by every worker. Before a request is dispatched, its
worst-case cost (estimated input at the uncached rate + the full output-token cap) is reserved.
Dispatch is refused when spent + reserved + the next reservation would exceed the cap.
"""

import csv
import json
import random
import threading
import time
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path

RATES_PATH = Path(__file__).resolve().parents[1] / "cost" / "rates.csv"
BILLED = ("input", "cached_input", "cache_write", "output")  # mutually exclusive token buckets


class BudgetExceeded(Exception):
    """Raised instead of dispatching a request that could push spend past the cap."""


def load_rates(path=RATES_PATH):
    """{model: {rate_type: Decimal usd per token}} from the editable, dated rates file."""
    rates = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            per_token = Decimal(row["usd_per_million_tokens"]) / Decimal(1_000_000)
            rates.setdefault(row["model"], {})[row["rate_type"]] = per_token
    return rates


def usage_cost(model, usage, rates):
    """Cost of one call. usage holds mutually exclusive buckets: input (uncached), cached_input,
    cache_write, output (reasoning already inside output). Unknown rates raise; never silently 0."""
    model_rates = rates[model]
    total = Decimal(0)
    for bucket in BILLED:
        n = usage.get(bucket, 0) or 0
        if n:
            if bucket not in model_rates:
                raise KeyError(f"no {bucket} rate for {model} in rates.csv")
            total += model_rates[bucket] * n
    return total


def worst_case_cost(model, est_input_tokens, max_output_tokens, rates):
    r = rates[model]
    return r["input"] * est_input_tokens + r["output"] * max_output_tokens


def estimate_tokens(text):
    """Deliberately high token estimate for reservations: 1 token per 2 UTF-8 bytes."""
    return len(text.encode("utf-8")) // 2 + 16


@dataclass
class SpendLedger:
    cap_usd: Decimal
    log_path: Path | None = None
    spent: Decimal = Decimal(0)
    reserved: Decimal = Decimal(0)
    _open: dict = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)
    _next: int = 0

    def reserve(self, amount, note=""):
        amount = Decimal(amount)
        with self._lock:
            if self.spent + self.reserved + amount > self.cap_usd:
                self._write({"event": "refused", "usd": str(amount), "note": note})
                raise BudgetExceeded(
                    f"cap ${self.cap_usd}: spent ${self.spent:.6f} + reserved ${self.reserved:.6f} "
                    f"+ next ${amount:.6f} would exceed it"
                )
            self._next += 1
            token = self._next
            self._open[token] = amount
            self.reserved += amount
            self._write({"event": "reserve", "token": token, "usd": str(amount), "note": note})
            return token

    def settle(self, token, actual, note=""):
        actual = Decimal(actual)
        with self._lock:
            self.reserved -= self._open.pop(token)
            self.spent += actual
            self._write({"event": "settle", "token": token, "usd": str(actual), "note": note})

    def _write(self, event):
        if self.log_path is None:
            return
        event.update(spent=str(self.spent), reserved=str(self.reserved), cap=str(self.cap_usd), t=time.time())
        with open(self.log_path, "a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
            f.flush()


class RateLimiter:
    """Shared minimum spacing between request starts (requests per minute)."""

    def __init__(self, requests_per_minute):
        self.interval = 60.0 / requests_per_minute
        self._lock = threading.Lock()
        self._next_start = 0.0

    def wait(self):
        with self._lock:
            now = time.monotonic()
            start = max(now, self._next_start)
            self._next_start = start + self.interval
        if start > now:
            time.sleep(start - now)


def backoff_delay(attempt, base=1.0, cap=30.0, rng=random):
    """Exponential backoff with full jitter, bounded by cap. attempt starts at 1."""
    return rng.uniform(0, min(cap, base * 2 ** (attempt - 1)))
