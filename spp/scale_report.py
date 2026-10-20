"""Measured cost/time checkpoints from the real 100k run's call log (no model call).
The 500 and 10,000 refreshes are read from the same run as it passed those counts, not separate runs."""

import json
from decimal import Decimal
from pathlib import Path

from . import store


def scale_checkpoints(run_dir, marks=(500, 10_000, 50_000)):
    conn = store.connect_pipeline(Path(run_dir) / "state.sqlite")
    calls = [json.loads(r) for (r,) in conn.execute("SELECT row FROM calls ORDER BY rowid")]
    conn.close()
    enrich = sorted((c for c in calls if c["role"] == "enrich"), key=lambda c: c["t"])
    out, sent, cost, ok, failed = [], 0, Decimal(0), 0, 0
    t0 = enrich[0]["t"] - enrich[0]["latency_s"]
    pending = list(marks)
    for c in enrich:
        cost += Decimal(c["cost_usd"])
        if c["outcome"] == "succeeded":
            ok += 1
            sent += len(c["review_ids"])
        else:
            failed += 1
        while pending and sent >= pending[0]:
            out.append({"distinct_texts_labeled_by_model": pending[0], "enrich_cost_usd": round(float(cost), 4),
                        "usd_per_1000_texts": round(float(cost) * 1000 / sent, 4), "succeeded_requests": ok, "failed_requests": failed})
            pending.pop(0)
    by_role = {}
    for c in calls:
        r = by_role.setdefault(c["role"], {"requests": 0, "failed": 0, "cost_usd": Decimal(0), "input_tokens": 0, "output_tokens": 0})
        r["requests"] += 1
        r["failed"] += c["outcome"] == "failed"
        r["cost_usd"] += Decimal(c["cost_usd"])
        r["input_tokens"] += c["input_tokens"]
        r["output_tokens"] += c["output_tokens"]
    total = sum(r["cost_usd"] for r in by_role.values())
    return {"checkpoints": out, "final_texts_labeled_by_model": sent,
            "by_role": {k: {**v, "cost_usd": round(float(v["cost_usd"]), 4)} for k, v in by_role.items()},
            "total_api_cost_usd": round(float(total), 4)}
