"""`spp` command line. Phase 1: `prepare`. Phase 2: `compare` (plan by default; paid only with --confirm)."""

import argparse
import json
import sys
import time
from pathlib import Path

from .prepare import PrepareError, prepare


def main(argv=None):
    parser = argparse.ArgumentParser(prog="python -m spp", description="Spotify review triage pipeline")
    sub = parser.add_subparsers(dest="command", required=True)
    p = sub.add_parser("prepare", help="Ingest and verify a CSV, seed the state store. No model calls.")
    p.add_argument("--csv", required=True, type=Path, help="input CSV (any path)")
    p.add_argument("--run-dir", type=Path, help="output folder (default: runs/<csv name>)")
    p.add_argument("--expect-full", action="store_true", help="assert the full-corpus counts (auto when the file hash matches)")
    p.add_argument("--grading-dir", type=Path, default=Path("grading"), help="where ingestion.json goes (full file only)")
    c = sub.add_parser("compare", help="Phase 2 classifier comparison on dev records. Plans only unless --confirm.")
    c.add_argument("--configs", nargs="+", default=["luna-none", "luna-low", "haiku", "sonnet-low"])
    c.add_argument("--reference", type=Path, default=Path("evals/dev_reference_v1.jsonl"))
    c.add_argument("--csv", type=Path, default=Path("data_raw/analysis_10000.csv"))
    c.add_argument("--batch-size", type=int, default=20)
    c.add_argument("--budget", type=float, default=2.0, help="hard spend cap in USD for this command")
    c.add_argument("--out", type=Path, help="run folder (default evals/phase2/<UTC timestamp>)")
    c.add_argument("--confirm", action="store_true", help="make the paid calls")
    c.add_argument("--report", type=Path, metavar="RUN_DIR", help="rescore a saved run offline; no calls")
    r = sub.add_parser("run", help="Run pipeline stages on a prepared run folder. Paid stages need --confirm.")
    r.add_argument("--csv", required=True, type=Path)
    r.add_argument("--run-dir", required=True, type=Path)
    r.add_argument("--stages", default="scope,enrich,verify,group,rank,memo",
                   help="comma list from scope,enrich,verify,group,rank,memo")
    r.add_argument("--scope-n", type=int, help="declared number of nonempty reviews to classify (default: all)")
    r.add_argument("--include", type=Path, nargs="*", default=[], help="CSVs whose IDs are always in scope")
    r.add_argument("--primary", default="luna-low")
    r.add_argument("--fallback", default="sonnet-low", help="allowlisted fallback config, or none")
    r.add_argument("--fallback-fraction", type=float, default=0.02)
    r.add_argument("--verifier", default="haiku")
    r.add_argument("--verify-fraction", type=float, default=0.01)
    r.add_argument("--group-model", default="luna-low")
    r.add_argument("--memo-model", default="sonnet-low")
    r.add_argument("--workers", type=int, default=1)
    r.add_argument("--batch-size", type=int, default=50)
    r.add_argument("--rpm", type=float, default=120, help="shared requests-per-minute limit across workers")
    r.add_argument("--budget", type=float, required=True, help="hard USD cap for all spend in this run folder")
    r.add_argument("--phase", choices=["initial", "resume"], help="enrichment phase label (default: auto)")
    r.add_argument("--stop-after-batches", type=int, help="interrupt deliberately after N enrichment requests")
    r.add_argument("--confirm", action="store_true", help="allow paid model calls")

    k = sub.add_parser("checkpoint", help="Snapshot completed IDs (no model call)")
    k.add_argument("--run-dir", required=True, type=Path)
    k.add_argument("--name", required=True, choices=["checkpoint_before", "checkpoint_after"])

    rr = sub.add_parser("rerank", help="Regenerate ranking, claims and aggregates from saved files (no model call)")
    rr.add_argument("--run-dir", required=True, type=Path)

    ex = sub.add_parser("export", help="Write the grading/ folder from a run folder (no model call)")
    ex.add_argument("--run-dir", required=True, type=Path)
    ex.add_argument("--grading-dir", type=Path, default=Path("grading"))
    ex.add_argument("--ingestion", type=Path, default=Path("grading/ingestion.json"))

    rq = sub.add_parser("requeue", help="Return reviews quarantined only by transport errors (e.g. 429) to pending (no model call)")
    rq.add_argument("--run-dir", required=True, type=Path)

    st = sub.add_parser("status", help="Show record counts, spend and calls for a run folder")
    st.add_argument("--run-dir", required=True, type=Path)

    co = sub.add_parser("cost", help="Cost calculator: offline replay (default) or the paid pilot")
    co.add_argument("action", choices=["replay", "pilot"], nargs="?", default="replay")
    co.add_argument("--budget", type=float, default=1.0)
    co.add_argument("--confirm", action="store_true")
    sy = sub.add_parser("synthetic", help="Injection test (paid, 1 request) and planted-error test (offline)")
    sy.add_argument("--run-dir", required=True, type=Path)
    sy.add_argument("--model", default="luna-none")
    sy.add_argument("--budget", type=float, default=0.10)
    sy.add_argument("--confirm", action="store_true")

    ge = sub.add_parser("golden", help="Score saved predictions against the hand-labeled golden 50 (no model call)")
    ge.add_argument("--run-dir", required=True, type=Path)
    ge.add_argument("--out", type=Path, default=Path("evals/golden"))
    dl = sub.add_parser("db-load", help="Load a finished run folder into Postgres (SUPABASE_DB_URL); no model call")
    dl.add_argument("--run-dir", required=True, type=Path)
    dc = sub.add_parser("dashboard-check", help="Check the deployed dashboard API matches saved files")
    dc.add_argument("--url", required=True)
    dc.add_argument("--run-dir", required=True, type=Path)
    args = parser.parse_args(argv)

    if args.command == "db-load":
        from .dbload import db_load
        print(json.dumps(db_load(args.run_dir), indent=2, default=str))
        return 0
    if args.command == "dashboard-check":
        from .dbload import dashboard_check
        from .atomic import atomic_write_json
        rep = dashboard_check(args.url, args.run_dir)
        atomic_write_json(Path("evals/dashboard_check.json"), rep)
        print(json.dumps(rep, indent=2))
        return 0 if rep["status"] == "pass" else 1
    if args.command == "golden":
        from .golden import golden_eval
        rep = golden_eval(args.run_dir, args.out)
        print((args.out / "golden_eval.md").read_text())
        return 0
    if args.command == "synthetic":
        from . import pipeline, synthetic
        from .providers import get_spec
        out = Path("evals/synthetic")
        print(json.dumps({k: v for k, v in synthetic.planted_error_test(args.run_dir, out).items() if k != "planted_rows"}, indent=2))
        if args.confirm:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parents[1] / ".env")
            ctx = pipeline.make_ctx(args.run_dir, args.budget, 60)
            ctx["ledger"].spent = 0  # separate small cap for the synthetic test
            rep = synthetic.injection_test(get_spec(args.model), ctx, out)
            print(f"injection test: {rep['passed']}/{rep['total']} resisted")
        else:
            print("injection test skipped (paid): add --confirm")
        return 0
    if args.command == "compare":
        return _compare(args)
    if args.command in ("run", "checkpoint", "rerank", "export", "status", "cost", "requeue"):
        return _pipeline_cmd(args)

    if args.command == "prepare":
        run_dir = args.run_dir or Path("runs") / args.csv.stem
        start = time.perf_counter()
        try:
            result = prepare(args.csv, run_dir, expect_full=args.expect_full, grading_dir=args.grading_dir)
        except PrepareError as e:
            print(f"PREPARE FAILED: {e}", file=sys.stderr)
            return 1
        rep = result["report"]
        print(f"input        {args.csv}  sha256={result['manifest']['input_file_sha256'][:12]}...")
        for k, v in rep["verified_counts"].items():
            print(f"  {k:26s} {v:>9,}")
        exp = rep["expectation"]
        print("full-count assertion:", "PASSED" if exp["ok"] else "not applied (not the full file)")
        print("states      ", rep["state_after_seed"]["statuses"])
        print(f"run dir      {run_dir}")
        if result["grading_ingestion"]:
            print("wrote        ", result["grading_ingestion"])
        print(f"elapsed      {time.perf_counter() - start:.1f}s")
    return 0


def _compare(args):
    from . import compare
    from .providers import get_spec

    refs, items = compare.load_dev(args.reference, args.csv)
    if args.report:
        summary, choice = compare.report(args.report, refs)
        print((args.report / "report.md").read_text())
        return 0
    if not 1 <= args.batch_size <= 50:
        print("batch size must be 1..50", file=sys.stderr)
        return 1
    for name in args.configs:
        get_spec(name)  # refuses anything off the allowlist
    rows, total = compare.plan(args.configs, items, args.batch_size)
    print(f"{len(items)} dev reviews, batch size {args.batch_size}, 1 worker")
    for r in rows:
        print(f"  {r['config']:11s} {r['label_config']:60s} requests={r['requests']}  worst case ${r['worst_case_usd']}")
    print(f"worst case total ${float(total):.4f} (assumes every review is retried once); cap ${args.budget}")
    if not args.confirm:
        print("PLAN ONLY: no model was called. Re-run with --confirm to make paid calls.")
        return 0
    from dotenv import load_dotenv

    load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    import time as _t
    out = args.out or Path("evals/phase2") / _t.strftime("%Y%m%dT%H%M%SZ", _t.gmtime())
    summary, choice = compare.run(args.configs, items, refs, args.batch_size, args.budget, out)
    print((out / "report.md").read_text())
    return 0


def _pipeline_cmd(args):
    import json
    from . import analysis, pipeline, store

    if args.command == "checkpoint":
        n = pipeline.checkpoint(args.run_dir, args.run_dir / "checkpoints" / f"{args.name}.json")
        print(f"{args.name}: {n} completed IDs")
        return 0
    if args.command == "rerank":
        rows, claims, _, _ = analysis.rank(args.run_dir)
        import hashlib
        digest = hashlib.sha256((args.run_dir / "outputs" / "ranking.csv").read_bytes()).hexdigest()
        print(f"{len(rows)} ranked issues, {len(claims)} claims; ranking.csv sha256 {digest}")
        return 0
    if args.command == "export":
        print(analysis.export(args.run_dir, args.grading_dir, args.ingestion))
        return 0
    if args.command == "requeue":
        conn = store.connect_pipeline(args.run_dir / "state.sqlite")
        with conn:
            n = conn.execute("UPDATE records SET status='pending', reason=NULL WHERE status='quarantined' AND reason LIKE 'transport_failed%'").rowcount
        print(f"requeued {n} reviews quarantined by transport errors; their failed calls stay in the log")
        return 0
    if args.command == "status":
        conn = store.connect_pipeline(args.run_dir / "state.sqlite")
        print(json.dumps({"statuses": store.status_counts(conn),
                          "scope": conn.execute("SELECT COUNT(*) FROM scope").fetchone()[0],
                          "cache_aliases": conn.execute("SELECT COUNT(*) FROM records WHERE cache_source_id IS NOT NULL").fetchone()[0],
                          "calls_by_role": dict(conn.execute("SELECT role || ':' || outcome, COUNT(*) FROM calls GROUP BY 1")),
                          "spent_usd": store.get_meta(conn, "spent_usd")}, indent=2))
        return 0
    if args.command == "cost":
        from . import cost
        if args.action == "replay":
            cost.replay()
            print((cost.COST / "report.md").read_text())
            return 0
        if not args.confirm:
            print("PLAN ONLY: the pilot runs cost_100.csv cold then warm (about $0.05 expected). Add --confirm to run it.")
            return 0
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
        print(json.dumps(cost.run_pilot(args.budget), indent=2))
        return 0

    # run
    from .providers import get_spec
    stages = [x.strip() for x in args.stages.split(",") if x.strip()]
    paid = {"enrich", "verify", "group", "memo"} & set(stages)
    if paid and not args.confirm:
        print(f"PLAN ONLY: stages {sorted(paid)} make paid calls; nothing was called. Add --confirm (cap ${args.budget}).")
        return 0
    if paid:
        from dotenv import load_dotenv
        load_dotenv(Path(__file__).resolve().parents[1] / ".env")
    texts = None
    def get_texts():
        nonlocal texts
        if texts is None:
            texts = pipeline.load_texts(args.csv)
        return texts
    ctx = pipeline.make_ctx(args.run_dir, args.budget, args.rpm)
    cache = args.run_dir / "downstream_cache"
    for stage in stages:
        if stage == "scope":
            n = pipeline.set_scope(args.run_dir, args.csv, n=args.scope_n, include_csvs=args.include)
            print(f"scope: {n} reviews declared")
        elif stage == "enrich":
            out = pipeline.enrich(args.run_dir, get_texts(), get_spec(args.primary), get_spec(args.fallback) if args.fallback != "none" else None,
                                  ctx, phase=args.phase, workers=args.workers, batch_size=args.batch_size,
                                  fallback_fraction=args.fallback_fraction, stop_after_batches=args.stop_after_batches)
            if out["interrupted"]:
                print("enrichment stopped early (interrupt, budget or --stop-after-batches); later stages skipped. Rerun to resume.")
                return 0
        elif stage == "verify":
            pipeline.verify(args.run_dir, get_texts(), get_spec(args.verifier), ctx, args.verify_fraction, workers=args.workers)
            rep = pipeline.verify_report(args.run_dir)
            from .atomic import atomic_write_json
            atomic_write_json(args.run_dir / "outputs" / "verification.json", rep)
            print("verification:", {k: rep[k] for k in ("n_verified", "topic_agreement", "intent_agreement", "severity_exact", "severity_within_1")})
        elif stage == "group":
            analysis.group(args.run_dir, get_texts(), get_spec(args.group_model), ctx, cache_dir=cache)
        elif stage == "rank":
            rows, claims, _, _ = analysis.rank(args.run_dir)
            print(f"rank: {len(rows)} issues; top 5: " + ", ".join(f"{r['issue_id']}={r['priority_score']}" for r in rows[:5]))
        elif stage == "memo":
            analysis.memo(args.run_dir, get_texts(), get_spec(args.memo_model), ctx, cache_dir=cache)
            print(f"memo written: {args.run_dir / 'outputs' / 'memo.md'}")
    conn = store.connect_pipeline(args.run_dir / "state.sqlite")
    with conn:
        pipeline.save_spent(conn, ctx)  # persist group/memo spend too
    conn.close()
    print(f"spent in this run folder: ${ctx['ledger'].spent:.4f} of ${args.budget}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
