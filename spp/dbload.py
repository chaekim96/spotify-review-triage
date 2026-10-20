"""Load a finished run folder into Postgres (Supabase). Offline: reads saved files only, no model call.
The recommendation is the memo generated once offline; the dashboard never calls a model."""

import csv
import json
import os
import re
import time
from pathlib import Path

from . import store
from .analysis import AREAS, CLAIM, ISSUE
from .pipeline import load_records

SCHEMA = Path(__file__).resolve().parents[1] / "db" / "schema.sql"


def db_load(run_dir, dsn=None, log=print):
    import psycopg
    from dotenv import load_dotenv
    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    if not dsn:
        # the Vercel-Supabase integration writes POSTGRES_URL_NON_POOLING into dashboard/.env.local (git-ignored)
        from dotenv import dotenv_values
        vercel_env = dotenv_values(Path(__file__).resolve().parents[1] / "dashboard" / ".env.local")
        dsn = os.environ.get("SUPABASE_DB_URL") or vercel_env.get("POSTGRES_URL_NON_POOLING")
    if not dsn:
        raise SystemExit("No database URL: set SUPABASE_DB_URL in .env or connect Supabase through Vercel")
    run_dir = Path(run_dir)
    out = run_dir / "outputs"
    conn = store.connect_pipeline(run_dir / "state.sqlite")
    recs = load_records(conn, completed_only=False)
    statuses = store.status_counts(conn)
    scope_n = conn.execute("SELECT COUNT(*) FROM scope").fetchone()[0]
    spent = store.get_meta(conn, "spent_usd")
    calls = dict(conn.execute("SELECT role || ':' || outcome, COUNT(*) FROM calls GROUP BY 1"))
    conn.close()
    with open(out / "membership.csv", newline="", encoding="utf-8") as f:
        membership = [(r["issue_id"], r["review_id"]) for r in csv.DictReader(f)]
    issue_of = {rid: iid for iid, rid in membership}
    issues = json.loads((out / "issues.json").read_text())
    with open(out / "ranking.csv", newline="", encoding="utf-8") as f:
        ranking = list(csv.DictReader(f))
    with open(out / "claims.csv", newline="", encoding="utf-8") as f:
        claims = list(csv.DictReader(f))
    agg = json.loads((out / "aggregates.json").read_text())
    memo_md = (out / "memo.md").read_text()
    memo_meta = json.loads((out / "memo_meta.json").read_text())
    verification = json.loads((out / "verification.json").read_text()) if (out / "verification.json").exists() else {}
    summary = {
        "statuses_all_660622": statuses, "scope_reviews": scope_n, "spent_usd": spent, "calls": calls,
        "completed_in_scope": agg["completed_records"], "complaint_or_cancellation": agg["complaint_or_cancellation_records"],
        "intent_counts": agg["intent_counts"], "topic_counts": agg["topic_counts"], "issue_count": agg["issue_count"],
        "cache_aliases": sum(1 for r in recs.values() if r.get("cache_source_id")),
        "verification": {k: verification.get(k) for k in ("n_verified", "topic_agreement", "intent_agreement", "severity_exact", "severity_within_1")},
    }
    rows = [r for r in recs.values() if r["status"] == "completed"]
    with psycopg.connect(dsn, autocommit=False) as pg, pg.cursor() as cur:
        cur.execute(SCHEMA.read_text())
        with cur.copy("COPY records (review_id, source_sha256, status, reason, topic, intent, sentiment, severity, entities, "
                      "evidence_quote, needs_review, label_config, cache_source_id, issue_id) FROM STDIN") as cp:
            for r in rows:
                cp.write_row((r["review_id"], r["source_sha256"], "completed", None, r["topic"], r["intent"], r["sentiment"], r["severity"],
                              json.dumps(r["entities"], ensure_ascii=False), r["evidence_quote"], r["needs_review"], r["label_config"],
                              r.get("cache_source_id"), issue_of.get(r["review_id"])))
        cur.executemany("INSERT INTO issues VALUES (%s,%s,%s,%s,%s,%s)",
                        [(d["issue_id"], d["topic"], AREAS[d["topic"]], d["name"], d["description"], json.dumps(d["keywords"])) for d in issues])
        with cur.copy("COPY membership (issue_id, review_id) FROM STDIN") as cp:
            for iid, rid in membership:
                cp.write_row((iid, rid))
        cur.executemany("INSERT INTO ranking VALUES (%s,%s,%s,%s,%s,%s)",
                        [(int(r["rank"]), r["issue_id"], int(r["complaint_count"]), int(r["severity_sum"]), r["mean_severity"], int(r["priority_score"])) for r in ranking])
        cur.executemany("INSERT INTO claims VALUES (%s,%s,%s,%s)", [(c["claim_id"], c["issue_id"], c["metric"], c["value"]) for c in claims])
        cur.executemany("INSERT INTO area_aggregates VALUES (%s,%s,%s,%s,%s,%s,%s)",
                        [(n, a["complaint_count"], a["severity_sum"], a["mean_severity"], a["share_of_severity_pct"], a["cancellation_count"], a["severity_4_plus"])
                         for n, a in agg["areas"].items()])
        cur.execute("INSERT INTO recommendations (generated_utc, model_config, recommended_area, memo_markdown, cited_claim_ids, cited_issue_ids, evidence_review_ids) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s)",
                    (time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime((out / "memo.md").stat().st_mtime)), memo_meta["config"], memo_meta["recommended_area"],
                     memo_md, json.dumps(sorted(set(CLAIM.findall(memo_md)))), json.dumps(sorted(set(ISSUE.findall(memo_md)))),
                     json.dumps(memo_meta["evidence_review_ids"])))
        cur.executemany("INSERT INTO run_summary VALUES (%s,%s)", [(k, json.dumps(v)) for k, v in summary.items()])
        # read-only access for the API: anon role may select, nothing else
        for t in ("run_summary", "records", "issues", "membership", "ranking", "claims", "area_aggregates", "recommendations"):
            cur.execute(f"alter table {t} enable row level security")
            cur.execute(f"create policy read_{t} on {t} for select using (true)")
        pg.commit()
    log(f"loaded {len(rows)} records, {len(issues)} issues, {len(membership)} memberships, {len(ranking)} ranked, {len(claims)} claims")
    return summary


def dashboard_check(base_url, run_dir):
    """Test that the deployed dashboard API serves exactly the saved numbers. No model call."""
    import urllib.request
    out = Path(run_dir) / "outputs"

    def get(path):
        with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=30) as r:
            return json.loads(r.read())
    with open(out / "ranking.csv", newline="", encoding="utf-8") as f:
        saved_rank = [{k: r[k] for k in ("rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score")} for r in csv.DictReader(f)]
    with open(out / "claims.csv", newline="", encoding="utf-8") as f:
        saved_claims = list(csv.DictReader(f))
    agg = json.loads((out / "aggregates.json").read_text())
    api_rank = [{k: str(r[k]) for k in ("rank", "issue_id", "complaint_count", "severity_sum", "mean_severity", "priority_score")} for r in get("/api/ranking")]
    api_claims = [{k: c[k] for k in ("claim_id", "issue_id", "metric", "value")} for c in get("/api/claims")]
    summ = get("/api/summary")
    api_areas = {a["area"]: a for a in summ["areas"]}
    problems = []
    if api_rank != saved_rank:
        problems.append("ranking differs from outputs/ranking.csv")
    if api_claims != saved_claims:
        problems.append("claims differ from outputs/claims.csv")
    for name, a in agg["areas"].items():
        b = api_areas.get(name)
        if not b or any(str(b[k]) != str(a[k]) for k in ("complaint_count", "severity_sum", "mean_severity", "share_of_severity_pct")):
            problems.append(f"area {name} differs from outputs/aggregates.json")
    if summ["summary"].get("completed_in_scope") != agg["completed_records"]:
        problems.append("completed count differs")
    rec = get("/api/recommendation")["recommendation"]
    if rec is None or rec["memo_markdown"].strip() != (out / "memo.md").read_text().strip():
        problems.append("recommendation differs from outputs/memo.md")
    return {"base_url": base_url, "checked": ["ranking", "claims", "areas", "completed count", "memo"], "problems": problems,
            "status": "pass" if not problems else "fail"}
