"""`spp` command line. Phase 1: `prepare`. Phase 2: `compare` (plan by default; paid only with --confirm)."""

import argparse
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
    args = parser.parse_args(argv)

    if args.command == "compare":
        return _compare(args)

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

    load_dotenv()
    import time as _t
    out = args.out or Path("evals/phase2") / _t.strftime("%Y%m%dT%H%M%SZ", _t.gmtime())
    summary, choice = compare.run(args.configs, items, refs, args.batch_size, args.budget, out)
    print((out / "report.md").read_text())
    return 0


if __name__ == "__main__":
    sys.exit(main())
