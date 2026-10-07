"""`spp` command line. Phase 1 provides `prepare`; later phases add enrich, verify, group, rank, recommend."""

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
    args = parser.parse_args(argv)

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


if __name__ == "__main__":
    sys.exit(main())
