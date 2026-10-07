# Spotify Review Triage

A multi-agent LLM pipeline over 660,622 Spotify app reviews (May 2022 to Nov 2023). It classifies every review, verifies a sample, groups complaints into issues, ranks them, and writes a recommendation.
Final deliverable for the MBA 290T final assignment. Status: Phase 1 (prepare) done; Phase 2 (labels and classifier design) built, paid comparison not yet run.

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

## Phase 2: labels and classifier design

Versioned files in `prompts/` (hashes pinned in `prompts/VERSIONS.json`; a changed prompt must become a new version):

- `labels_v1.md`: the 8 topics, 5 intents (precedence), 1 to 5 severity, sentiment, entities, quote and needs_review rules, plus the extra rules in DECISIONS D21.
- `examples_v1.jsonl`: 15 worked examples from development rows, each with a one-line reason.
- `enrich_v1.md`: classifier role prompt (definitions + examples). `verify_v1.md`: independent verifier role prompt (definitions only, never sees the first labels).

Code: `spp/labels.py` (schema, prompt assembly, validation), `spp/providers.py` (model allowlist; OpenAI and Anthropic adapters), `spp/budget.py` (dated rates, shared spend ledger, rate limiter, backoff), `spp/runner.py` (batches of at most 50, retry invalid output once, then quarantine), `spp/evaluate.py` (scoring), `spp/compare.py`.

Compare candidate models on the 94-row development reference (`evals/dev_reference_v1.jsonl`, labeled by the assistant, never the golden 50):

```sh
uv run python -m spp compare                     # plan only: batches and worst-case cost, no calls
uv run python -m spp compare --confirm --budget 2 # paid: needs keys in .env, capped at $2
uv run python -m spp compare --report evals/phase2/<run>   # rescore saved outputs offline
```

The golden 50 (`golden_50_to_label.csv`) is labeled by hand and only used for the final eval; its IDs and texts are refused as development input and a test checks none appear in the prompts.

Design decisions are in [DECISIONS.md](DECISIONS.md).
