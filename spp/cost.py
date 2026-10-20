"""100-review cost and runtime calculator (COST_CALCULATOR.md).

`replay` (default) recomputes everything from cost/usage.csv, cost/rates.csv and cost/assumptions.json with no key
and no model call. `pilot --confirm` runs the real cold and warm pilots on cost_100.csv and saves the evidence.
"""

import csv
import json
import shutil
import time
from collections import defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from .atomic import atomic_write_json, atomic_write_text
from .budget import load_rates

ROOT = Path(__file__).resolve().parents[1]
COST = ROOT / "cost"
USAGE_COLS = ["run_id", "request_id", "stage", "provider_model", "config", "outcome", "n_reviews",
              "input", "cached_input", "cache_write", "output", "reasoning_info_only", "latency_s"]


def _d(x):
    return Decimal(str(x))


def _money(x, places="0.0001"):
    return str(_d(x).quantize(Decimal(places), ROUND_HALF_UP))


# ---------------------------------------------------------------- measured pilot

def run_pilot(budget_usd=1.0, log=print):
    """Cold run (empty result cache, 1 worker, all stages) then warm run (saved result cache). Paid."""
    from . import pipeline, store
    from .analysis import group, memo, rank
    from .prepare import prepare
    from .providers import get_spec

    csv_path = ROOT / "data_raw" / "cost_100.csv"
    specs = {"primary": get_spec("luna-none"), "fallback": get_spec("sonnet-low"), "verify": get_spec("haiku"),
             "group": get_spec("luna-low"), "memo": get_spec("sonnet-low")}  # DECISIONS D27/D33
    downstream_cache = ROOT / "runs" / "pilot_downstream_cache"
    summary = {}
    for run_id in ("pilot_cold", "pilot_warm"):
        run_dir = ROOT / "runs" / run_id
        if run_dir.exists():
            shutil.rmtree(run_dir)
        if run_id == "pilot_cold" and downstream_cache.exists():
            shutil.rmtree(downstream_cache)  # cold means empty result and artifact caches
        t_start = time.perf_counter()
        stage_t = {}
        t = time.perf_counter()
        prepare(csv_path, run_dir)
        pipeline.set_scope(run_dir, csv_path)
        texts = pipeline.load_texts(csv_path)
        stage_t["prepare"] = time.perf_counter() - t
        ctx = pipeline.make_ctx(run_dir, budget_usd, rpm=120)
        t = time.perf_counter()
        enr = pipeline.enrich(run_dir, texts, specs["primary"], specs["fallback"], ctx, phase="initial", workers=1,
                              cache_db=(ROOT / "runs" / "pilot_cold" / "state.sqlite") if run_id == "pilot_warm" else None, log=log)
        stage_t["enrich"] = time.perf_counter() - t
        t = time.perf_counter()
        pipeline.verify(run_dir, texts, specs["verify"], ctx, fraction=0.20, workers=1,
                        cache_db=(ROOT / "runs" / "pilot_cold" / "state.sqlite") if run_id == "pilot_warm" else None, log=log)
        stage_t["verify"] = time.perf_counter() - t
        t = time.perf_counter()
        group(run_dir, texts, specs["group"], ctx, cache_dir=downstream_cache, log=log)
        stage_t["group"] = time.perf_counter() - t
        t = time.perf_counter()
        rank(run_dir)
        stage_t["rank"] = time.perf_counter() - t
        t = time.perf_counter()
        memo(run_dir, texts, specs["memo"], ctx, cache_dir=downstream_cache, log=log)
        stage_t["memo"] = time.perf_counter() - t
        conn = store.connect_pipeline(run_dir / "state.sqlite")
        counts = store.status_counts(conn)
        calls = [json.loads(r) for (r,) in conn.execute("SELECT row FROM calls ORDER BY rowid")]
        conn.close()
        summary[run_id] = {
            "wall_seconds": round(time.perf_counter() - t_start, 2), "stage_seconds": {k: round(v, 2) for k, v in stage_t.items()},
            "statuses": counts, "requests": len(calls),
            "enrich_requests": sum(c["role"] == "enrich" for c in calls),
            "failed_requests": sum(c["outcome"] == "failed" for c in calls),
            "result_cache_hits": enr.get("result_cache_hits_from_cache_db", 0), "cache_aliases_within_run": enr["cache_aliases"],
            "spent_usd": str(ctx["ledger"].spent), "workers": 1, "batch_size": 50,
            "configs": {k: ({"model": s.model, "effort": s.effort} if s else None) for k, s in specs.items()},
        }
    _save_pilot_evidence(summary)
    return summary


def _save_pilot_evidence(summary):
    from . import store
    from .pipeline import load_records
    COST.mkdir(exist_ok=True)
    conn = store.connect_pipeline(ROOT / "runs" / "pilot_cold" / "state.sqlite")
    recs = load_records(conn, completed_only=False)
    conn.close()
    atomic_write_text(COST / "pilot_records.jsonl", "".join(json.dumps(r, ensure_ascii=False) + "\n" for r in recs.values()))
    calls_out, usage_rows = [], []
    for run_id in ("pilot_cold", "pilot_warm"):
        conn = store.connect_pipeline(ROOT / "runs" / run_id / "state.sqlite")
        for (row,) in conn.execute("SELECT row FROM calls ORDER BY rowid"):
            c = json.loads(row)
            c["run_id"] = run_id
            calls_out.append(c)
            u = c.get("usage") or {}
            usage_rows.append([run_id, c["request_id"], c["role"], c["model"], c.get("config"), c["outcome"], len(c["review_ids"]),
                               u.get("input", 0), u.get("cached_input", 0), u.get("cache_write", 0), u.get("output", 0),
                               u.get("reasoning") if u.get("reasoning") is not None else "", c.get("latency_s")])
        conn.close()
    atomic_write_text(COST / "pilot_calls.jsonl", "".join(json.dumps(c, ensure_ascii=False) + "\n" for c in calls_out))
    with open(COST / "usage.csv", "w", newline="", encoding="utf-8") as f:
        w = csv.writer(f, lineterminator="\n")
        w.writerow(USAGE_COLS)
        w.writerows(usage_rows)
    atomic_write_json(COST / "pilot_summary.json", summary)


# ---------------------------------------------------------------- offline replay

def load_usage(path=COST / "usage.csv"):
    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f))


def call_cost(row, rates):
    r = rates[row["provider_model"]]
    total = Decimal(0)
    for bucket in ("input", "cached_input", "cache_write", "output"):  # mutually exclusive; reasoning is inside output
        n = int(row[bucket] or 0)
        if n:
            total += r[bucket] * n
    return total


def replay(rates_path=COST / "rates.csv", usage_path=COST / "usage.csv", assumptions_path=COST / "assumptions.json",
           summary_path=COST / "pilot_summary.json", out_path=COST / "report.md"):
    rates = load_rates(rates_path)
    usage = load_usage(usage_path)
    A = json.loads(Path(assumptions_path).read_text())
    S = json.loads(Path(summary_path).read_text())
    by = defaultdict(lambda: defaultdict(lambda: {"requests": 0, "failed": 0, "cost": Decimal(0), "reviews": 0,
                                                  "input": 0, "cached_input": 0, "output": 0}))
    for row in usage:
        s = by[row["run_id"]][row["stage"]]
        s["requests"] += 1
        s["failed"] += row["outcome"] == "failed"
        s["cost"] += call_cost(row, rates)
        s["reviews"] += int(row["n_reviews"])
        for k in ("input", "cached_input", "output"):
            s[k] += int(row[k] or 0)
    cold, warm = by["pilot_cold"], by.get("pilot_warm", {})
    cold_total = sum(s["cost"] for s in cold.values())
    warm_total = sum(s["cost"] for s in warm.values())
    # per-unit measurements from the cold run
    enrich_reviews_sent = max(1, cold["enrich"]["reviews"])
    distinct_cold = A["pilot_distinct_texts"]
    enrich_per_distinct = cold["enrich"]["cost"] / distinct_cold          # includes retries and fallback that actually happened
    verify_per_review = cold["verify"]["cost"] / max(1, cold["verify"]["reviews"]) if "verify" in cold else Decimal(0)
    group_per_call = cold["group"]["cost"] / max(1, cold["group"]["requests"]) if "group" in cold else Decimal(0)
    memo_once = cold["memo"]["cost"] if "memo" in cold else Decimal(0)
    enrich_secs = S["pilot_cold"]["stage_seconds"]["enrich"]
    reviews_per_sec_1w = Decimal(distinct_cold) / _d(enrich_secs) if enrich_secs else Decimal(0)

    scen_rows = []
    for target in A["targets"]:
        for scen in ("base", "conservative"):
            k = A["scenarios"][scen]
            for reuse in (True, False):
                work = target["distinct_texts"] if reuse else target["nonempty"]
                enrich = enrich_per_distinct * work * _d(k["retry_multiplier"]) * _d(k["output_multiplier"])
                fallback_extra = Decimal(0)
                if k["fallback_fraction"] > 0:
                    fb = A["fallback_cost_per_review_usd"]
                    fallback_extra = _d(fb) * work * _d(k["fallback_fraction"])
                verify = verify_per_review * int(target["nonempty"] * A["verify_fraction"]) * _d(k["retry_multiplier"])
                group_c = group_per_call * A["group_calls"]
                total = enrich + fallback_extra + verify + group_c + memo_once
                secs = (Decimal(work) / (reviews_per_sec_1w * A["max_concurrency"])) if reviews_per_sec_1w else None
                scen_rows.append({"target": target["name"], "scenario": scen, "reuse": reuse, "work_items": work,
                                  "enrich": _money(enrich), "fallback": _money(fallback_extra), "verify": _money(verify),
                                  "group": _money(group_c), "memo": _money(memo_once), "total_usd": _money(total, "0.01"),
                                  "est_minutes": str((secs / 60).quantize(Decimal("0.1"))) if secs is not None else "unknown",
                                  "over_budget": total > _d(A["budget_usd"][target["name"]])})
    lines = [
        "# Cost and runtime calculator: 100-review pilot",
        "",
        f"Generated offline from `cost/usage.csv`, `cost/rates.csv` (dated rates, editable) and `cost/assumptions.json`. No key, no model call.",
        f"Input `cost_100.csv` sha256 `{A['pilot_sha256']}`; 100 IDs; {distinct_cold} distinct texts.",
        "",
        "## Measured (real pilot)",
        "",
        "| run | stage | requests | failed | reviews sent | input tok | cached input tok | output tok | cost $ |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for run_id, stages in by.items():
        for stage, s in stages.items():
            lines.append(f"| {run_id} | {stage} | {s['requests']} | {s['failed']} | {s['reviews']} | {s['input']} | {s['cached_input']} | {s['output']} | {_money(s['cost'], '0.000001')} |")
    for run_id in ("pilot_cold", "pilot_warm"):
        if run_id in S:
            s = S[run_id]
            lines.append("")
            lines.append(f"**{run_id}**: wall clock {s['wall_seconds']} s; stages {json.dumps(s['stage_seconds'])}; statuses {json.dumps(s['statuses'])}; "
                         f"enrichment requests {s['enrich_requests']}; result-cache hits {s['result_cache_hits']}; workers {s['workers']}; batch size {s['batch_size']}.")
    lines += ["", f"Cold total ${_money(cold_total, '0.000001')} (${_money(cold_total * 1000 / 100, '0.0001')} per 1,000 input rows, "
              f"${_money(cold_total / 100, '0.000001')} per record). Warm incremental ${_money(warm_total, '0.000001')}.",
              f"Models and settings: {json.dumps(S['pilot_cold']['configs'])}.", "",
              "## Estimated (projections, not measurements)", "",
              f"Enrichment cost per distinct text {_money(enrich_per_distinct, '0.0000001')} (measured, includes real retries/fallback); "
              f"verification {A['verify_fraction']:.0%} of records; group calls {A['group_calls']} once; memo once; "
              f"max concurrency {A['max_concurrency']}; max fallback fraction {A['max_fallback_fraction']:.0%}; output-token cap {A['output_token_cap_per_review']} per review.",
              "",
              "| target | scenario | exact-text reuse | items sent | enrich $ | fallback $ | verify $ | group $ | memo $ | total $ | est. minutes | budget |",
              "|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for r in scen_rows:
        flag = "**OVER BUDGET**" if r["over_budget"] else "within"
        lines.append(f"| {r['target']} | {r['scenario']} | {'yes' if r['reuse'] else 'no'} | {r['work_items']} | {r['enrich']} | {r['fallback']} | "
                     f"{r['verify']} | {r['group']} | {r['memo']} | {r['total_usd']} | {r['est_minutes']} | {flag} (${A['budget_usd'][r['target']]}) |")
    lines += ["", "Local compute (laptop CPU, SQLite) is not billed and is not included above; its cost is unknown, not zero.",
              "Formulas: item_cost = billed_units x usd_per_token (per-million price / 1,000,000); input, cached input, cache writes and output are separate buckets; reasoning tokens are already inside output.", ""]
    atomic_write_text(out_path, "\n".join(lines) + "\n")
    return {"cold_total": cold_total, "warm_total": warm_total, "scenarios": scen_rows}
