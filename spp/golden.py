"""Golden-50 evaluation: the user's hand labels vs the pipeline's saved predictions. No model call.
Hand labels are only read here, after classification; they never reach prompts, examples, thresholds or grouping."""

import csv
import json
from pathlib import Path

from . import store
from .atomic import atomic_write_json, atomic_write_text
from .evaluate import SENTIMENT_STRICT_TOLERANCE, SENTIMENT_TOLERANCE, score
from .pipeline import load_records

GOLD_CSV = Path(__file__).resolve().parents[1] / "data_raw" / "golden_50_to_label.csv"


def _bool(v):
    return str(v).strip().lower() in ("true", "1", "yes", "y")


def load_gold(path=GOLD_CSV):
    gold, texts, problems = {}, {}, []
    with open(path, encoding="utf-8-sig", newline="") as f:
        for row in csv.DictReader(f):
            rid = row["review_id"]
            texts[rid] = row["review_text"]
            if not row.get("topic", "").strip():
                problems.append(f"{rid}: unlabeled")
                continue
            ents = row.get("entities", "").strip()
            try:
                ents = json.loads(ents) if ents.startswith("[") else [e.strip() for e in ents.split(";") if e.strip()]
            except ValueError:
                ents = [ents]
            gold[rid] = {"topic": row["topic"].strip(), "intent": row["intent"].strip(), "sentiment": float(row["sentiment"]),
                         "severity": int(float(row["severity"])), "entities": ents, "evidence_quote": row.get("evidence_quote", ""),
                         "needs_review": _bool(row.get("needs_review", "false"))}
    return gold, texts, problems


def golden_eval(run_dir, out_dir, path=GOLD_CSV):
    gold, texts, problems = load_gold(path)
    if not gold:
        raise SystemExit(f"no golden labels filled in {path} ({len(problems)} rows unlabeled)")
    conn = store.connect_pipeline(Path(run_dir) / "state.sqlite")
    recs = load_records(conn)
    conn.close()
    preds = {rid: {k: recs[rid][k] for k in ("topic", "intent", "sentiment", "severity", "entities", "evidence_quote", "needs_review")}
             for rid in gold if rid in recs}
    m = score(preds, gold)
    quote_checks = {
        "model_quotes_exact_substring": sum(1 for rid, p in preds.items() if p["evidence_quote"] and p["evidence_quote"] in texts[rid]),
        "human_quotes_exact_substring": sum(1 for rid, g in gold.items() if g["evidence_quote"] and g["evidence_quote"] in texts[rid]),
        "n": len(gold),
    }
    report = {"n_gold": len(gold), "unlabeled_rows": problems, "metrics": {k: v for k, v in m.items() if k != "disagreements"},
              "quote_checks": quote_checks, "sentiment_tolerances": [SENTIMENT_TOLERANCE, SENTIMENT_STRICT_TOLERANCE],
              "disagreements": [{**d, "review_text": texts[d["review_id"]]} for d in m["disagreements"]]}
    out_dir = Path(out_dir)
    atomic_write_json(out_dir / "golden_eval.json", report)
    # checker-format gold file (one accepted label per field, as the user labeled)
    cases = [{"review_id": rid, "status": "approved", "reviewer": "course student (hand labels)",
              "accepted_topic": [g["topic"]], "accepted_intent": [g["intent"]], "accepted_severity": [g["severity"]]}
             for rid, g in gold.items()]
    atomic_write_json(out_dir / "gold_for_checker.json", {"version": "a5-audit-v1", "cases": cases})
    mm = report["metrics"]
    lines = ["# Golden-50 evaluation", "",
             f"{len(gold)} hand-labeled reviews vs saved pipeline predictions (missing predictions count as wrong).", "",
             "| metric | value |", "|---|---|"]
    for k in ("coverage", "topic_agreement", "intent_agreement", "severity_exact", "severity_within_1", "severity_mae_on_predicted",
              "sentiment_mae_on_predicted", f"sentiment_within_{SENTIMENT_TOLERANCE}", f"sentiment_within_{SENTIMENT_STRICT_TOLERANCE}",
              "needs_review_agreement", "topic_macro_f1_present_classes"):
        lines.append(f"| {k} | {mm.get(k)} |")
    lines += ["", f"Quotes: model {quote_checks['model_quotes_exact_substring']}/{len(preds)} exact substrings; "
              f"human {quote_checks['human_quotes_exact_substring']}/{len(gold)}.", "", "## Per-topic", "",
              "| topic | support | precision | recall | F1 |", "|---|---|---|---|---|"]
    for t, v in mm["per_topic"].items():
        lines.append(f"| {t} | {v['support']} | {v['precision']} | {v['recall']} | {v['f1']} |")
    lines += ["", "## Confusion (human -> model)", "", ", ".join(f"{k}: {v}" for k, v in mm["confusion"].items()), "",
              "## Disagreements", ""]
    for d in report["disagreements"]:
        p = d["pred"] or {}
        lines.append(f"- `{d['review_id']}` fields {d['fields']}: human {d['ref']['topic']}/{d['ref']['intent']}/sev {d['ref']['severity']}, "
                     f"model {p.get('topic')}/{p.get('intent')}/sev {p.get('severity')}. Text: {json.dumps(d['review_text'][:200], ensure_ascii=False)}")
    atomic_write_text(out_dir / "golden_eval.md", "\n".join(lines) + "\n")
    return report
