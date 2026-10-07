"""Phase 2: compare candidate classifier configurations on development records.

`plan` (default) only prints the batches and the worst-case cost; it makes no call.
`run --confirm` makes paid calls, capped by a spend ledger. `report` rescores saved outputs offline.
The golden-50 file is never read for labels; its IDs and texts are refused as dev inputs.
"""

import csv
import json
import time
from decimal import Decimal
from pathlib import Path

from .atomic import atomic_write_json, atomic_write_text
from .budget import RateLimiter, SpendLedger, estimate_tokens, load_rates, worst_case_cost
from .evaluate import SENTIMENT_STRICT_TOLERANCE, SENTIMENT_TOLERANCE, pairwise_agreement, score
from .labels import FIELDS, label_config, prompt_sha256, system_prompt, user_message
from .providers import get_spec
from .runner import classify_batch
from .vendored import csv_rows

ROOT = Path(__file__).resolve().parents[1]
GOLDEN_CSV = ROOT / "data_raw" / "golden_50_to_label.csv"
FULL_N, DISTINCT_N = 660_609, 484_189

# Declared before any paid run (DECISIONS D18): the cheapest config that is within 5 points of the
# best topic and intent agreement, has severity within +/-1 on >= 85% of rows, and returns valid
# output for >= 98% of reviews on the first attempt.
SELECTION_RULE = {"agreement_margin": 0.05, "severity_within_1_min": 0.85, "first_pass_valid_min": 0.98}


def golden_guard():
    """IDs and texts of the golden 50. Only the id/text columns are read, never the label columns."""
    ids, texts = set(), set()
    if GOLDEN_CSV.exists():
        with open(GOLDEN_CSV, encoding="utf-8-sig", newline="") as f:
            for row in csv.DictReader(f):
                ids.add(row["review_id"])
                texts.add(row["review_text"])
    return ids, texts


def load_dev(ref_path, csv_path):
    refs = {}
    for line in Path(ref_path).read_text(encoding="utf-8").splitlines():
        if line.strip():
            r = json.loads(line)
            refs[r["review_id"]] = {k: r[k] for k in FIELDS}
    texts = {}
    for row in csv_rows(csv_path):
        if row["review_id"] in refs:
            texts[row["review_id"]] = row["review_text"]
    missing = set(refs) - set(texts)
    if missing:
        raise SystemExit(f"{len(missing)} reference IDs not found in {csv_path}")
    g_ids, g_texts = golden_guard()
    leaked = [rid for rid in refs if rid in g_ids or texts[rid] in g_texts]
    if leaked:
        raise SystemExit(f"refusing: {len(leaked)} dev rows match golden IDs or texts: {leaked[:5]}")
    order = list(refs)
    return refs, [(rid, texts[rid]) for rid in order]


def batches_of(items, size):
    return [items[i:i + size] for i in range(0, len(items), size)]


def plan(configs, items, batch_size):
    rates = load_rates()
    rows, total = [], Decimal(0)
    for name in configs:
        spec = get_spec(name)
        system = system_prompt("enrich")[1]
        worst = sum(
            worst_case_cost(spec.model, estimate_tokens(system + user_message(b)), spec.max_output_tokens(len(b)), rates)
            for b in batches_of(items, batch_size)
        )
        # one invalid-output retry of every review is the true worst case
        worst *= 2
        total += worst
        rows.append({"config": name, "model": spec.model, "effort": spec.effort,
                     "label_config": label_config(spec.model, spec.effort),
                     "requests": len(batches_of(items, batch_size)), "worst_case_usd": round(float(worst), 4)})
    return rows, total


def run(configs, items, refs, batch_size, budget_usd, out_dir, rpm=30):
    out_dir.mkdir(parents=True, exist_ok=True)
    rates = load_rates()
    ledger = SpendLedger(Decimal(str(budget_usd)), log_path=out_dir / "ledger.jsonl")
    ctx = {"rates": rates, "ledger": ledger, "limiter": RateLimiter(rpm)}
    meta = {
        "started_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "configs": configs, "batch_size": batch_size, "budget_usd": budget_usd, "workers": 1,
        "n_reviews": len(items), "reference": "evals/dev_reference_v1.jsonl (assistant-labeled dev rows, not golden)",
        "enrich_prompt_sha256": prompt_sha256("enrich"),
    }
    atomic_write_json(out_dir / "run_meta.json", meta)
    calls_path = out_dir / "calls.jsonl"
    for name in configs:
        spec = get_spec(name)
        preds, quarantine = {}, {}
        t0 = time.perf_counter()
        for b in batches_of(items, batch_size):
            done, quar, logs = classify_batch(spec, "enrich", b, ctx, phase="initial")
            preds.update(done)
            quarantine.update(quar)
            with open(calls_path, "a", encoding="utf-8") as f:
                for row in logs:
                    f.write(json.dumps(row, ensure_ascii=False) + "\n")
            # save after every batch
            atomic_write_text(out_dir / f"predictions_{name}.jsonl",
                              "".join(json.dumps({"review_id": k, **v}, ensure_ascii=False) + "\n" for k, v in preds.items()))
            atomic_write_json(out_dir / f"quarantine_{name}.json", quarantine)
        meta.setdefault("wall_seconds", {})[name] = round(time.perf_counter() - t0, 2)
        atomic_write_json(out_dir / "run_meta.json", meta)
    meta["spent_usd"] = str(ledger.spent)
    atomic_write_json(out_dir / "run_meta.json", meta)
    return report(out_dir, refs)


def _load_preds(path):
    if not path.exists():
        return {}
    return {r["review_id"]: {k: r[k] for k in FIELDS}
            for r in (json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip())}


def report(out_dir, refs):
    """Rebuild summary.json and report.md from saved files only (no model call)."""
    out_dir = Path(out_dir)
    meta = json.loads((out_dir / "run_meta.json").read_text())
    calls = [json.loads(l) for l in (out_dir / "calls.jsonl").read_text().splitlines() if l.strip()]
    summary, preds_by = {}, {}
    for name in meta["configs"]:
        preds = _load_preds(out_dir / f"predictions_{name}.jsonl")
        preds_by[name] = preds
        qpath = out_dir / f"quarantine_{name}.json"
        quar = json.loads(qpath.read_text()) if qpath.exists() else {}
        mine = [c for c in calls if c["config"] == name]
        n_items = meta["n_reviews"]
        # first-pass validity: reviews neither re-sent for invalid output nor quarantined
        first_pass_ok = n_items - len(_retried_ids(mine) | set(quar))
        cost = sum(Decimal(c["cost_usd"]) for c in mine)
        m = score(preds, refs)
        per_review = cost / n_items if n_items else Decimal(0)
        summary[name] = {
            "model": mine[0]["model"] if mine else None, "label_config": mine[0]["label_config"] if mine else None,
            "requests": len(mine), "failed_requests": sum(c["outcome"] == "failed" for c in mine),
            "quarantined": len(quar), "quarantine_reasons": sorted({q["reason"] for q in quar.values()}),
            "first_pass_valid_rate": round(first_pass_ok / n_items, 4),
            "input_tokens": sum(c["input_tokens"] for c in mine), "output_tokens": sum(c["output_tokens"] for c in mine),
            "reasoning_tokens": sum((c["usage"] or {}).get("reasoning") or 0 for c in mine),
            "cost_usd_measured": round(float(cost), 6),
            "wall_seconds": meta.get("wall_seconds", {}).get(name),
            "estimate_full_run_no_reuse_usd": round(float(per_review * FULL_N), 2),
            "estimate_full_run_with_reuse_usd": round(float(per_review * DISTINCT_N), 2),
            "metrics": {k: v for k, v in m.items() if k not in ("disagreements", "per_topic", "confusion")},
            "per_topic": m["per_topic"], "confusion": m["confusion"],
        }
        atomic_write_json(out_dir / f"disagreements_{name}.json", m["disagreements"])
    names = list(summary)
    pairs = {f"{a}~{b}": pairwise_agreement(preds_by[a], preds_by[b]) for i, a in enumerate(names) for b in names[i + 1:]}
    choice = select(summary)
    atomic_write_json(out_dir / "summary.json", {"configs": summary, "pairwise": pairs, "selection_rule": SELECTION_RULE, "selected": choice})
    atomic_write_text(out_dir / "report.md", _markdown(meta, summary, pairs, choice))
    return summary, choice


def _retried_ids(calls):
    """Reviews that needed an invalid-output retry = IDs sent in a second successful request."""
    seen, retried = set(), set()
    for c in calls:
        if c["outcome"] != "succeeded":
            continue
        for rid in c["review_ids"]:
            (retried if rid in seen else seen).add(rid)
    return retried


def select(summary):
    ok = {n: s for n, s in summary.items() if s["requests"]}
    if not ok:
        return None
    best_topic = max(s["metrics"]["topic_agreement"] for s in ok.values())
    best_intent = max(s["metrics"]["intent_agreement"] for s in ok.values())
    eligible = [
        n for n, s in ok.items()
        if s["metrics"]["topic_agreement"] >= best_topic - SELECTION_RULE["agreement_margin"]
        and s["metrics"]["intent_agreement"] >= best_intent - SELECTION_RULE["agreement_margin"]
        and s["metrics"]["severity_within_1"] >= SELECTION_RULE["severity_within_1_min"]
        and s["first_pass_valid_rate"] >= SELECTION_RULE["first_pass_valid_min"]
    ]
    if not eligible:
        return {"config": None, "why": "no configuration met the declared rule"}
    pick = min(eligible, key=lambda n: ok[n]["cost_usd_measured"])
    return {"config": pick, "eligible": eligible, "why": "cheapest configuration meeting the declared rule"}


def _markdown(meta, summary, pairs, choice):
    lines = [
        "# Phase 2 classifier comparison (development records)",
        "",
        f"Run started {meta['started_utc']}; {meta['n_reviews']} dev reviews; batch size {meta['batch_size']}; 1 worker; budget cap ${meta['budget_usd']}.",
        f"Reference: {meta['reference']}. Agreement is measured against assistant labels, so it is a consistency check, not human accuracy.",
        "Measured values come from saved provider usage. Full-run figures are estimates (cost per review x row count).",
        "",
        f"| config | model | topic | intent | sev exact | sev ±1 | sev MAE | sent MAE | sent ±{SENTIMENT_TOLERANCE} | sent ±{SENTIMENT_STRICT_TOLERANCE} | needs_review | 1st-pass valid | quarantined | cost $ | sec | est. full $ (no reuse / reuse) |",
        "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|",
    ]
    for n, s in summary.items():
        m = s["metrics"]
        lines.append(
            f"| {n} | {s['model']} | {m['topic_agreement']} | {m['intent_agreement']} | {m['severity_exact']} | {m['severity_within_1']} | "
            f"{m['severity_mae_on_predicted']} | {m['sentiment_mae_on_predicted']} | {m[f'sentiment_within_{SENTIMENT_TOLERANCE}']} | "
            f"{m[f'sentiment_within_{SENTIMENT_STRICT_TOLERANCE}']} | {m['needs_review_agreement']} | {s['first_pass_valid_rate']} | {s['quarantined']} | "
            f"{s['cost_usd_measured']} | {s['wall_seconds']} | {s['estimate_full_run_no_reuse_usd']} / {s['estimate_full_run_with_reuse_usd']} |"
        )
    lines += ["", "## Pairwise agreement between configurations", "", "| pair | n | topic | intent | severity | sentiment MAE |", "|---|---|---|---|---|---|"]
    for k, p in pairs.items():
        if p.get("n_shared"):
            lines.append(f"| {k} | {p['n_shared']} | {p['topic']} | {p['intent']} | {p['severity']} | {p['sentiment_mae']} |")
    lines += ["", "## Selection", "", f"Rule (declared before the run): {json.dumps(SELECTION_RULE)}", f"Result: {json.dumps(choice)}", ""]
    return "\n".join(lines) + "\n"
