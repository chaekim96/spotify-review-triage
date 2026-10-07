"""Score predictions against reference labels. Pure code, no model call; reused for the dev
comparison now and for the golden-50 eval once the human labels exist.

Missing or quarantined predictions stay in every denominator (they count as wrong)."""

from collections import Counter
from decimal import ROUND_HALF_UP, Decimal

from .labels import TOPICS

SENTIMENT_TOLERANCE = 0.5          # predeclared (DECISIONS D12)
SENTIMENT_STRICT_TOLERANCE = 0.25  # stricter figure also reported


def _r(x, places=4):
    return float(Decimal(str(x)).quantize(Decimal(1).scaleb(-places), rounding=ROUND_HALF_UP))


def score(preds, refs):
    """preds: {review_id: labels}; refs: {review_id: labels}. Returns a metrics dict."""
    n = len(refs)
    if n == 0:
        raise ValueError("no reference rows")
    have = [rid for rid in refs if rid in preds]
    c = Counter()
    sev_err, sent_err = [], []
    confusion = Counter()
    disagreements = []
    for rid, ref in refs.items():
        p = preds.get(rid)
        if p is None:
            confusion[(ref["topic"], "<missing>")] += 1
            disagreements.append({"review_id": rid, "fields": ["missing"], "ref": ref, "pred": None})
            continue
        diffs = []
        for f in ("topic", "intent", "severity", "needs_review"):
            if p[f] == ref[f]:
                c[f] += 1
            else:
                diffs.append(f)
        confusion[(ref["topic"], p["topic"])] += 1
        se = abs(p["severity"] - ref["severity"])
        sev_err.append(se)
        c["severity_within_1"] += se <= 1
        de = abs(p["sentiment"] - ref["sentiment"])
        sent_err.append(de)
        c["sentiment_within_tol"] += de <= SENTIMENT_TOLERANCE + 1e-9
        c["sentiment_within_strict"] += de <= SENTIMENT_STRICT_TOLERANCE + 1e-9
        if de > SENTIMENT_TOLERANCE + 1e-9:
            diffs.append("sentiment")
        if diffs:
            disagreements.append({"review_id": rid, "fields": diffs, "ref": ref, "pred": p})
    per_topic = {}
    for t in TOPICS:
        tp = confusion[(t, t)]
        fp = sum(v for (r, pr), v in confusion.items() if pr == t and r != t)
        fn = sum(v for (r, pr), v in confusion.items() if r == t and pr != t)
        support = sum(v for (r, _), v in confusion.items() if r == t)
        prec = tp / (tp + fp) if tp + fp else 0.0
        rec = tp / (tp + fn) if tp + fn else 0.0
        f1 = 2 * prec * rec / (prec + rec) if prec + rec else 0.0
        per_topic[t] = {"support": support, "precision": _r(prec), "recall": _r(rec), "f1": _r(f1)}
    present = [t for t in TOPICS if per_topic[t]["support"]]
    return {
        "n_reference": n,
        "n_predicted": len(have),
        "coverage": _r(len(have) / n),
        "topic_agreement": _r(c["topic"] / n),
        "intent_agreement": _r(c["intent"] / n),
        "severity_exact": _r(c["severity"] / n),
        "severity_within_1": _r(c["severity_within_1"] / n),
        "severity_mae_on_predicted": _r(sum(sev_err) / len(sev_err)) if sev_err else None,
        "sentiment_mae_on_predicted": _r(sum(sent_err) / len(sent_err)) if sent_err else None,
        f"sentiment_within_{SENTIMENT_TOLERANCE}": _r(c["sentiment_within_tol"] / n),
        f"sentiment_within_{SENTIMENT_STRICT_TOLERANCE}": _r(c["sentiment_within_strict"] / n),
        "needs_review_agreement": _r(c["needs_review"] / n),
        "topic_macro_f1_present_classes": _r(sum(per_topic[t]["f1"] for t in present) / len(present)) if present else None,
        "per_topic": per_topic,
        "confusion": {f"{r}->{p}": v for (r, p), v in sorted(confusion.items())},
        "disagreements": disagreements,
    }


def pairwise_agreement(a, b):
    """Field agreement between two prediction sets on their shared IDs (no reference needed)."""
    shared = sorted(set(a) & set(b))
    if not shared:
        return {"n_shared": 0}
    out = {"n_shared": len(shared)}
    for f in ("topic", "intent", "severity", "needs_review"):
        out[f] = _r(sum(a[r][f] == b[r][f] for r in shared) / len(shared))
    out["sentiment_mae"] = _r(sum(abs(a[r]["sentiment"] - b[r]["sentiment"]) for r in shared) / len(shared))
    return out
