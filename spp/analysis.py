"""Group -> rank -> claims -> memo -> export. Code owns membership, arithmetic, ranking and claim checks;
the group model only names issues from a bounded evidence pack, and the memo model only sees saved aggregates."""

import csv
import hashlib
import io
import json
import random
import re
import shutil
from collections import Counter, defaultdict
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from . import store
from .atomic import atomic_write_bytes, atomic_write_json, atomic_write_text
from .labels import PROMPTS_DIR, TOPICS
from .pipeline import load_records
from .runner import logged_call
from .vendored import checker

COMPLAINT_INTENTS = ("complaint", "cancellation")
AREAS = {  # DECISIONS D24: the 8 contract topics folded into the 4 business areas
    "access": "access", "usability": "usability", "catalog": "usability",
    "playback": "playback", "downloads": "playback", "billing": "billing/support", "support": "billing/support",
    "other": "unassigned (general)",
}
PACK_PER_TOPIC = 80
GROUP_PROMPT = "group_v2"  # v1 keywords were long literal phrases that left large catch-alls (DECISIONS D34)
MIN_FOR_MODEL = 8
MEMO_TOP_ISSUES = 12
mean_string = checker.mean_string


def _csv_text(header, rows):
    buf = io.StringIO()
    w = csv.writer(buf, lineterminator="\n")
    w.writerow(header)
    w.writerows(rows)
    return buf.getvalue()


def _cached(cache_dir, key, fn):
    """Downstream artifact cache keyed by the exact inputs and configuration."""
    if cache_dir:
        p = Path(cache_dir) / f"{key}.json"
        if p.exists():
            return json.loads(p.read_text()), True
    value = fn()
    if cache_dir and value is not None:
        Path(cache_dir).mkdir(parents=True, exist_ok=True)
        atomic_write_json(Path(cache_dir) / f"{key}.json", value)
    return value, False


def _log_calls(run_dir, rows):
    if not rows:
        return
    conn = store.connect_pipeline(Path(run_dir) / "state.sqlite")
    with conn:
        for row in rows:
            conn.execute("INSERT OR REPLACE INTO calls(request_id, role, phase, outcome, row) VALUES(?,?,?,?,?)",
                         (row["request_id"], row["role"], row["phase"], row["outcome"], json.dumps(row, ensure_ascii=False)))
    conn.close()
    with open(Path(run_dir) / "calls.jsonl", "a", encoding="utf-8") as f:
        for row in rows:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")


# ---------------------------------------------------------------- group

GROUP_SCHEMA = {
    "type": "object",
    "properties": {"issues": {"type": "array", "items": {
        "type": "object",
        "properties": {"name": {"type": "string"}, "description": {"type": "string"},
                       "keywords": {"type": "array", "items": {"type": "string"}}},
        "required": ["name", "description", "keywords"], "additionalProperties": False}}},
    "required": ["issues"], "additionalProperties": False,
}


def group(run_dir, texts, spec, ctx, cache_dir=None, log=print):
    run_dir = Path(run_dir)
    out_dir = run_dir / "outputs"
    conn = store.connect_pipeline(run_dir / "state.sqlite")
    recs = load_records(conn)
    conn.close()
    complaints = {rid: r for rid, r in recs.items() if r["intent"] in COMPLAINT_INTENTS}
    by_topic = defaultdict(list)
    for rid, r in complaints.items():
        by_topic[r["topic"]].append(rid)
    system = (PROMPTS_DIR / f"{GROUP_PROMPT}.md").read_text(encoding="utf-8")
    cfg = f"{spec.model}+{spec.effort}+{GROUP_PROMPT.replace('_', '-')}"
    issues, model_calls, cache_hits = [], 0, 0
    for topic in TOPICS:
        rids = sorted(by_topic.get(topic, []))
        if not rids:
            continue
        defs = []
        if len(rids) >= MIN_FOR_MODEL:
            pack = sorted(random.Random(f"{GROUP_PROMPT}:{topic}").sample(rids, min(PACK_PER_TOPIC, len(rids))))
            user = json.dumps({"topic": topic, "complaints": [
                {"review_id": r, "quote": complaints[r]["evidence_quote"], "text": texts[r][:200]} for r in pack]}, ensure_ascii=False)
            key = "group-" + hashlib.sha256((cfg + system + user).encode()).hexdigest()[:24]

            def run_model():
                parsed, rows = logged_call(spec, "group", system, user, GROUP_SCHEMA, "issue_groups", 1500, ctx, pack, cfg)
                _log_calls(run_dir, rows)
                return parsed
            parsed, hit = _cached(cache_dir, key, run_model)
            cache_hits += hit
            model_calls += not hit
            for i, it in enumerate((parsed or {}).get("issues", [])[:7], 1):
                kws = [k.strip().lower() for k in it["keywords"] if k.strip()]
                if kws:
                    defs.append({"issue_id": f"{topic.upper()}-{i:02d}", "topic": topic, "name": it["name"].strip(),
                                 "description": it["description"].strip(), "keywords": kws, "source": "model:" + cfg})
        defs.append({"issue_id": f"{topic.upper()}-99", "topic": topic, "name": f"Other {topic} complaints",
                     "description": f"Complaints labeled {topic} that match none of the named {topic} issues.",
                     "keywords": [], "source": "code catch-all"})
        issues.extend(defs)
    membership = assign(complaints, texts, issues)
    atomic_write_json(out_dir / "issues.json", issues)
    atomic_write_text(out_dir / "membership.csv",
                      _csv_text(["issue_id", "review_id"], sorted((iid, rid) for rid, iid in membership.items())))
    log(f"group: {len(complaints)} complaint/cancellation records -> {len(issues)} issues; model calls {model_calls}, cache hits {cache_hits}")
    return issues, membership


def assign(complaints, texts, issues):
    """Deterministic: first issue (in saved order) of the record's topic whose keyword is a substring of the
    lowercased review text; otherwise the topic's catch-all. One issue per complaint."""
    by_topic = defaultdict(list)
    for d in issues:
        by_topic[d["topic"]].append(d)
    # a keyword must start at a word boundary ("ads" must not match inside "downloads"); stems like "shuffl" still match
    pats = {d["issue_id"]: re.compile("|".join(r"(?<![a-z0-9])" + re.escape(k) for k in d["keywords"])) for d in issues if d["keywords"]}
    out = {}
    for rid, r in complaints.items():
        low = texts[rid].lower()
        chosen = None
        for d in by_topic[r["topic"]]:
            if d["keywords"] and pats[d["issue_id"]].search(low):
                chosen = d["issue_id"]
                break
        out[rid] = chosen or f"{r['topic'].upper()}-99"
    return out


# ---------------------------------------------------------------- rank (code only)

def rank(run_dir):
    """Rebuild ranking, aggregates and claims from saved files only. No model call."""
    run_dir = Path(run_dir)
    out_dir = run_dir / "outputs"
    conn = store.connect_pipeline(run_dir / "state.sqlite")
    recs = load_records(conn)
    scope_n = conn.execute("SELECT COUNT(*) FROM scope").fetchone()[0]
    conn.close()
    with open(out_dir / "membership.csv", newline="", encoding="utf-8") as f:
        membership = [(r["issue_id"], r["review_id"]) for r in csv.DictReader(f)]
    issues = {d["issue_id"]: d for d in json.loads((out_dir / "issues.json").read_text())}
    sev = defaultdict(list)
    for iid, rid in membership:
        sev[iid].append(recs[rid]["severity"])
    rows = [{"issue_id": iid, "complaint_count": len(v), "severity_sum": sum(v),
             "mean_severity": mean_string(sum(v), len(v)), "priority_score": sum(v)} for iid, v in sev.items()]
    rows.sort(key=lambda x: (-x["priority_score"], x["issue_id"]))
    for i, r in enumerate(rows, 1):
        r["rank"] = i
    cols = ["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"]
    atomic_write_text(out_dir / "ranking.csv", _csv_text(cols, [[r[c] for c in cols] for r in rows]))
    claims = []
    for r in rows:
        for metric in ("complaint_count", "severity_sum", "mean_severity", "priority_score"):
            claims.append({"claim_id": f"C{len(claims) + 1:04d}", "issue_id": r["issue_id"], "metric": metric, "value": str(r[metric])})
    atomic_write_text(out_dir / "claims.csv", _csv_text(["claim_id", "issue_id", "metric", "value"],
                                                         [[c["claim_id"], c["issue_id"], c["metric"], c["value"]] for c in claims]))
    # area-level aggregates (other quantities, explained separately from the four contract metrics)
    completed = [r for r in recs.values() if r["status"] == "completed"]
    complaints = [r for r in completed if r["intent"] in COMPLAINT_INTENTS]
    total_sev = sum(r["severity"] for r in complaints)
    area = defaultdict(lambda: {"complaint_count": 0, "severity_sum": 0, "cancellation_count": 0, "severity_4_plus": 0})
    for r in complaints:
        a = area[AREAS[r["topic"]]]
        a["complaint_count"] += 1
        a["severity_sum"] += r["severity"]
        a["cancellation_count"] += r["intent"] == "cancellation"
        a["severity_4_plus"] += r["severity"] >= 4
    for name, a in area.items():
        a["mean_severity"] = mean_string(a["severity_sum"], a["complaint_count"])
        a["share_of_severity_pct"] = str((Decimal(100 * a["severity_sum"]) / Decimal(total_sev)).quantize(Decimal("0.1"), ROUND_HALF_UP)) if total_sev else "0.0"
        a["issues"] = sorted({iid for iid, rid in membership if AREAS[recs[rid]["topic"]] == name})
    aggregates = {
        "scope_reviews": scope_n, "completed_records": len(completed),
        "complaint_or_cancellation_records": len(complaints), "total_severity": total_sev,
        "intent_counts": dict(Counter(r["intent"] for r in completed)),
        "topic_counts": dict(Counter(r["topic"] for r in completed)),
        "areas": dict(sorted(area.items())), "issue_count": len(rows),
    }
    atomic_write_json(out_dir / "aggregates.json", aggregates)
    atomic_write_text(out_dir / "aggregates.csv", _csv_text(
        ["area", "complaint_count", "severity_sum", "mean_severity", "share_of_severity_pct", "cancellation_count", "severity_4_plus"],
        [[n, a["complaint_count"], a["severity_sum"], a["mean_severity"], a["share_of_severity_pct"], a["cancellation_count"], a["severity_4_plus"]]
         for n, a in sorted(area.items())]))
    return rows, claims, aggregates, issues


# ---------------------------------------------------------------- memo

MEMO_SCHEMA = {
    "type": "object",
    "properties": {"memo_markdown": {"type": "string"}, "recommended_area": {"type": "string"},
                   "cited_claim_ids": {"type": "array", "items": {"type": "string"}}},
    "required": ["memo_markdown", "recommended_area", "cited_claim_ids"], "additionalProperties": False,
}
NUM = re.compile(r"(?<![\w.\-])\d[\d,]*(?:\.\d+)?(?![\w\-])")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
ISSUE = re.compile(r"\b[A-Z]+-\d{2}\b")
CLAIM = re.compile(r"\bC\d{4}\b")


def memo_inputs(run_dir, texts):
    out_dir = Path(run_dir) / "outputs"
    rows, claims, aggregates, issues = rank(run_dir)
    claim_ids = defaultdict(dict)
    for c in claims:
        claim_ids[c["issue_id"]][c["metric"]] = c["claim_id"]
    top = rows[:MEMO_TOP_ISSUES]
    conn = store.connect_pipeline(Path(run_dir) / "state.sqlite")
    recs = load_records(conn)
    conn.close()
    with open(out_dir / "membership.csv", newline="", encoding="utf-8") as f:
        members = defaultdict(list)
        for r in csv.DictReader(f):
            members[r["issue_id"]].append(r["review_id"])
    evidence = []
    for r in top[:6]:
        ids = sorted(members[r["issue_id"]], key=lambda x: (-recs[x]["severity"], x))
        for x in ids[:2]:  # by severity then ID, so identical inputs give an identical pack (and a downstream cache hit)
            evidence.append({"review_id": x, "issue_id": r["issue_id"], "quote": recs[x]["evidence_quote"][:240]})
    payload = {
        "scope": f"{aggregates['scope_reviews']} reviews in the declared classification scope; {aggregates['completed_records']} completed records",
        "areas": [{"area": n, **{k: a[k] for k in ("complaint_count", "severity_sum", "mean_severity", "share_of_severity_pct",
                                                   "cancellation_count", "severity_4_plus")}} for n, a in aggregates["areas"].items()],
        "intent_counts": aggregates["intent_counts"],
        "top_issues": [{"rank": r["rank"], "issue_id": r["issue_id"], "name": issues[r["issue_id"]]["name"],
                        "area": AREAS[issues[r["issue_id"]]["topic"]], "topic": issues[r["issue_id"]]["topic"],
                        **{m: {"value": str(r[m]), "claim_id": claim_ids[r["issue_id"]][m]}
                           for m in ("complaint_count", "severity_sum", "mean_severity")}} for r in top],
        "evidence_pack": evidence,
    }
    allowed_numbers = set()

    def collect(v):
        if isinstance(v, dict):
            for x in v.values():
                collect(x)
        elif isinstance(v, list):
            for x in v:
                collect(x)
        elif isinstance(v, (int, float)) and not isinstance(v, bool):
            allowed_numbers.add(str(v))
        elif isinstance(v, str):
            for n in NUM.findall(v):
                allowed_numbers.add(n.replace(",", ""))
    collect({k: v for k, v in payload.items() if k != "evidence_pack"})
    allowed_numbers |= {c["value"] for c in claims}
    return payload, claims, issues, allowed_numbers


def check_memo(text, claims, issues, evidence_ids, allowed_numbers):
    """Reject any cited claim, issue or review ID, or any number, that is not in the saved calculations."""
    problems = []
    claim_set = {c["claim_id"] for c in claims}
    for cid in set(CLAIM.findall(text)):
        if cid not in claim_set:
            problems.append(f"unknown claim id {cid}")
    for iid in set(ISSUE.findall(text)):
        if iid not in issues:
            problems.append(f"unknown issue id {iid}")
    for uid in set(UUID.findall(text)):
        if uid not in evidence_ids:
            problems.append(f"review id not in evidence pack {uid}")
    scrubbed = UUID.sub(" ", CLAIM.sub(" ", ISSUE.sub(" ", text)))
    scrubbed = re.sub(r"^\s*\d+\.\s", " ", scrubbed, flags=re.M)  # numbered-list markers
    for n in NUM.findall(scrubbed):
        v = n.replace(",", "")
        if v not in allowed_numbers and not (v.isdigit() and int(v) <= 10):
            problems.append(f"number not in saved calculations: {n}")
    if not CLAIM.search(text):
        problems.append("memo cites no claim IDs")
    return sorted(set(problems))


def memo(run_dir, texts, spec, ctx, cache_dir=None, log=print):
    run_dir = Path(run_dir)
    out_dir = run_dir / "outputs"
    payload, claims, issues, allowed = memo_inputs(run_dir, texts)
    evidence_ids = {e["review_id"] for e in payload["evidence_pack"]}
    system = (PROMPTS_DIR / "memo_v1.md").read_text(encoding="utf-8")
    cfg = f"{spec.model}+{spec.effort}+memo-v1"
    base_user = json.dumps(payload, ensure_ascii=False, indent=1)
    feedback = ""
    for attempt in (1, 2):
        user = base_user + feedback
        key = "memo-" + hashlib.sha256((cfg + system + user).encode()).hexdigest()[:24]

        def run_model():
            parsed, rows = logged_call(spec, "memo", system, user, MEMO_SCHEMA, "memo", 4000, ctx, [], cfg)
            _log_calls(run_dir, rows)
            return parsed
        parsed, hit = _cached(cache_dir, key, run_model)
        if parsed is None:
            raise RuntimeError("memo model returned no usable output")
        problems = check_memo(parsed["memo_markdown"], claims, issues, evidence_ids, allowed)
        log(f"memo attempt {attempt}: {'cache hit' if hit else 'model call'}, {len(problems)} problems")
        if not problems:
            atomic_write_text(out_dir / "memo.md", parsed["memo_markdown"].strip() + "\n")
            atomic_write_json(out_dir / "memo_meta.json", {"config": cfg, "recommended_area": parsed["recommended_area"],
                                                           "cited_claim_ids": sorted(set(CLAIM.findall(parsed["memo_markdown"]))),
                                                           "evidence_review_ids": sorted(evidence_ids), "inputs": payload})
            return parsed
        feedback = "\n\nYour previous memo was rejected by the checker for: " + "; ".join(problems[:20]) + \
                   ". Rewrite it, using only numbers and IDs from the input."
    atomic_write_json(out_dir / "memo_rejected.json", {"problems": problems, "memo": parsed})
    raise RuntimeError(f"memo rejected after retry: {problems[:5]}")


# ---------------------------------------------------------------- export

RUN_JSON = {"version": "a5-audit-v1", "analysis_count": 660622,
            "analysis_sha256": "1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6",
            "classification_input_fields": ["review_text"], "allow_multi_issue": False}
CALL_FIELDS = ("request_id", "role", "review_ids", "model", "phase", "outcome", "label_config", "input_tokens", "output_tokens")


def export(run_dir, grading_dir, ingestion_src):
    run_dir, g = Path(run_dir), Path(grading_dir)
    g.mkdir(parents=True, exist_ok=True)
    out_dir = run_dir / "outputs"
    atomic_write_json(g / "run.json", RUN_JSON)
    if Path(ingestion_src).resolve() != (g / "ingestion.json").resolve():
        shutil.copyfile(ingestion_src, g / "ingestion.json")
    conn = store.connect_pipeline(run_dir / "state.sqlite")
    scope = {r for (r,) in conn.execute("SELECT review_id FROM scope")}
    recs = load_records(conn, completed_only=False)
    calls = [json.loads(r) for (r,) in conn.execute("SELECT row FROM calls ORDER BY rowid")]
    conn.close()
    lines = []
    for rid, r in recs.items():
        if r["status"] == "completed":
            row = {k: r[k] for k in ("review_id", "source_sha256", "status", "topic", "intent", "sentiment", "severity",
                                     "entities", "evidence_quote", "needs_review", "label_config")}
            if "cache_source_id" in r:
                row["cache_source_id"] = r["cache_source_id"]
        elif r["status"] == "quarantined":
            row = {"review_id": rid, "source_sha256": r["source_sha256"], "status": "quarantined", "reason": r["reason"]}
        else:
            reason = "not_classified_run_incomplete" if rid in scope else "not_classified_outside_declared_scope"
            row = {"review_id": rid, "source_sha256": r["source_sha256"], "status": "quarantined", "reason": reason}
        lines.append(json.dumps(row, ensure_ascii=False))
    import gzip
    (g / "records.jsonl").unlink(missing_ok=True)
    # gzip (allowed by the contract) keeps the 660,622-line file under GitHub's size limit; mtime=0 makes it reproducible
    atomic_write_bytes(g / "records.jsonl.gz", gzip.compress(("\n".join(lines) + "\n").encode("utf-8"), mtime=0))
    atomic_write_text(g / "calls.jsonl", "".join(json.dumps({k: c[k] for k in CALL_FIELDS}, ensure_ascii=False) + "\n" for c in calls))
    for name in ("membership.csv", "ranking.csv", "claims.csv"):
        shutil.copyfile(out_dir / name, g / name)
    for name in ("checkpoint_before.json", "checkpoint_after.json"):
        src = run_dir / "checkpoints" / name
        if src.exists():
            shutil.copyfile(src, g / name)
    return {"records": len(lines), "calls": len(calls)}


def rerank_from_grading(grading_dir):
    """Recompute ranking.csv and claims.csv from grading/records.jsonl(.gz) + membership.csv alone (no state, no
    model). Returns (ranking_text, claims_text) so callers can compare them byte for byte with the saved files."""
    import gzip
    g = Path(grading_dir)
    path = g / "records.jsonl.gz"
    opener = gzip.open if path.exists() else open
    sev = {}
    with opener(path if path.exists() else g / "records.jsonl", "rt", encoding="utf-8") as f:
        for line in f:
            r = json.loads(line)
            if r.get("status") == "completed":
                sev[r["review_id"]] = r["severity"]
    by_issue = defaultdict(list)
    with open(g / "membership.csv", newline="", encoding="utf-8") as f:
        for r in csv.DictReader(f):
            by_issue[r["issue_id"]].append(sev[r["review_id"]])
    rows = [{"issue_id": i, "complaint_count": len(v), "severity_sum": sum(v), "mean_severity": mean_string(sum(v), len(v)),
             "priority_score": sum(v)} for i, v in by_issue.items()]
    rows.sort(key=lambda x: (-x["priority_score"], x["issue_id"]))
    cols = ["rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score"]
    for k, r in enumerate(rows, 1):
        r["rank"] = k
    claims, n = [], 0
    for r in rows:
        for m in ("complaint_count", "severity_sum", "mean_severity", "priority_score"):
            n += 1
            claims.append([f"C{n:04d}", r["issue_id"], m, str(r[m])])
    return (_csv_text(cols, [[r[c] for c in cols] for r in rows]),
            _csv_text(["claim_id", "issue_id", "metric", "value"], claims))
