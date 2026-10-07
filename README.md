# Spotify Review Triage

A multi-agent LLM pipeline over 660,622 Spotify app reviews (May 2022 to Nov 2023). It classifies every review, verifies a sample, groups complaints into issues, ranks them, and writes a recommendation.
Final deliverable for the MBA 290T final assignment. Status: Phase 1 (prepare) only. Everything below the Phase 1 section is not built yet.

**Business question:** Where should Spotify put next quarter's product effort: access, usability, playback, or billing/support?
(Downloads and catalog issues are folded into the nearest of these four areas; see DECISIONS.md.)

## Setup

Needs [uv](https://docs.astral.sh/uv/). Python 3.12 is pinned in `.python-version`.

```sh
uv sync                      # creates .venv from uv.lock
cp .env.example .env         # then fill in only the keys you use; .env is git-ignored
uv run pytest                # offline tests, no keys needed
```

Keys (`OPENAI_API_KEY`, `ANTHROPIC_API_KEY`, `TYPESAFE_API_KEY`) are loaded from `.env` by python-dotenv. Phase 1 needs none and makes no model calls.

## Data

Dataset files are not in git. Put the course files in `data_raw/` and verify checksums; see [data_raw/README_PLACEMENT.md](data_raw/README_PLACEMENT.md).
Full file: `spotify_reviews_18months.csv`, 97,400,616 bytes, SHA-256 `1fc85de68a304dd8978b537cfa58793d5f41cbaf417fa32cb53899f83a2fcef6`.

## Phase 1: prepare (no model calls)

```sh
uv run python -m spp prepare --csv data_raw/spotify_reviews_18months.csv --run-dir runs/full
```

Takes any CSV path. It streams the file with the csv module (reviews contain embedded newlines), hashes every row with the course `row_sha`, runs the course profile helper, checks the counts, and seeds a SQLite state store.
For the full file (detected by hash, or forced with `--expect-full`) it asserts 660,622 rows, 13 empty texts, 159,701 missing app versions, 0 duplicate IDs, 484,189 distinct nonempty texts, and writes `grading/ingestion.json`.
Re-running is safe: completed rows are never reset, and a changed source row is refused.

Outputs in the run folder: `state.sqlite`, `data_manifest.json`, `ingestion_report.json`, `pending_ids.txt`.
`vendor/check_submission.py` is the instructor's checker, copied unmodified; the code imports `row_sha` and `profile` from it so hashing cannot drift.
Check the ingestion file offline:

```sh
uv run python vendor/check_submission.py profile --full data_raw/spotify_reviews_18months.csv --out /tmp/ingestion.json
cmp /tmp/ingestion.json grading/ingestion.json
```

Design decisions are in [DECISIONS.md](DECISIONS.md).
