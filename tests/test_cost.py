"""Calculator replay is offline and its arithmetic behaves as the instructor will test it."""

import csv
import json
from decimal import Decimal

from spp import cost


def _setup(tmp_path, rate_factor=1):
    rates = tmp_path / "rates.csv"
    with open(cost.COST / "rates.csv") as src, open(rates, "w") as dst:
        rows = list(csv.DictReader(src))
        w = csv.DictWriter(dst, fieldnames=rows[0].keys())
        w.writeheader()
        for r in rows:
            r["usd_per_million_tokens"] = str(Decimal(r["usd_per_million_tokens"]) * rate_factor)
            w.writerow(r)
    usage = tmp_path / "usage.csv"
    with open(usage, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(cost.USAGE_COLS)
        w.writerow(["pilot_cold", "r1", "enrich", "gpt-6-luna", "luna-none", "succeeded", 50, 3000, 2000, 0, 4000, 0, 3.0])
        w.writerow(["pilot_cold", "r2", "enrich", "gpt-6-luna", "luna-none", "succeeded", 50, 3000, 2000, 0, 4000, 0, 3.0])
        w.writerow(["pilot_cold", "r3", "verify", "claude-haiku-4-5-20251001", "haiku", "succeeded", 20, 2500, 0, 0, 1500, "", 4.0])
        w.writerow(["pilot_cold", "r4", "group", "gpt-6-luna", "luna-low", "succeeded", 40, 2000, 0, 0, 800, 300, 5.0])
        w.writerow(["pilot_cold", "r5", "memo", "claude-sonnet-5-5", "sonnet-low", "succeeded", 0, 3000, 0, 0, 1500, "", 20.0])
    summary = tmp_path / "s.json"
    summary.write_text(json.dumps({"pilot_cold": {"stage_seconds": {"enrich": 6.0}, "wall_seconds": 40, "statuses": {}, "enrich_requests": 2,
                                                  "result_cache_hits": 0, "workers": 1, "batch_size": 50, "configs": {}}}))
    return rates, usage, summary


def test_doubling_rates_doubles_api_cost_and_keeps_measurements(tmp_path):
    results = {}
    for factor in (1, 2):
        d = tmp_path / str(factor)
        d.mkdir()
        rates, usage, summary = _setup(d, factor)
        results[factor] = cost.replay(rates, usage, cost.COST / "assumptions.json", summary, d / "report.md")
    assert results[1]["cold_total"] > 0
    assert results[2]["cold_total"] == 2 * results[1]["cold_total"]


def test_mutually_exclusive_buckets():
    rates = cost.load_rates()
    row = {"provider_model": "gpt-6-luna", "input": "1000000", "cached_input": "1000000", "cache_write": "0", "output": "1000000"}
    assert cost.call_cost(row, rates) == Decimal("0.61")
