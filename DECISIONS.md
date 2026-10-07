# Decisions

Format: ID · date · decision · alternatives considered · what was measured · why · revisit trigger.

**D01 · 2026-10-07 · Python 3.12 managed by uv** · Alternatives: Anaconda 3.7.6 (the default `python3` here), pip + venv. Measured: `python3 --version` gave 3.7.6; the course dataset script uses `hashlib.file_digest` (Python 3.11+). Why: uv pins the version and writes `uv.lock`, so anyone can rebuild the same environment. The package runs from the repo root with `python -m spp` (no install step; an editable install broke on this Mac because the `.pth` file got a hidden flag). Revisit: if a dependency needs another Python.

**D02 · 2026-10-07 · Vendor `check_submission.py` unmodified into `vendor/`** · Alternatives: rewrite hashing ourselves; call the copy in `data_raw/`. Measured: vendored copy sha256 equals the data_raw copy (`d60bd66d...c26d`); the code refuses to import if it changes. Why: the contract says to use the provided `row_sha`, and `ingestion.json` must equal its `profile` output byte for byte. Revisit: if the instructor publishes a new checker version.

**D03 · 2026-10-07 · SQLite (WAL mode) as the state store** · Alternatives: JSONL checkpoints, Postgres/Supabase for state. Measured: seeding 660,622 rows takes about 12 to 28 s and the file is about 250 MB. Why: one transaction per batch gives safe resume with no partial writes, and it needs no server. User chose SQLite. Statuses are explicit: `pending`, `completed`, `quarantined` (CHECK constraint). Revisit: if concurrent writers become a bottleneck.

**D04 · 2026-10-07 · Pending queue is `pending_ids.txt` (one review_id per line, source order)** · Alternatives: `pending_queue.jsonl` with full rows; count only. Measured: 660,609 IDs, 24 MB. Why: the SQLite table is the real source of truth; the file is a simple, diffable export that is rebuilt from the database on every run, so it never goes stale. It holds IDs only, not review text, so it cannot leak data or drift from the CSV. Revisit: if batching needs the text next to the ID (then read the CSV by ID).

**D05 · 2026-10-07 · Parse CSV with Python's `csv` module, `utf-8-sig`, `newline=""`, strict** · Alternatives: line-based reading, pandas. Measured: the full file has 660,792 physical lines but 660,622 rows (170 embedded newlines). Why: it is the exact way the checker reads the file, so row counts and hashes match; no trimming or Unicode normalization. "Empty text" means `not text.strip()`, as in the checker; all 13 are also literally empty. Revisit: never for the graded file.

**D06 · 2026-10-07 · Keys held: OpenAI and Anthropic only (no TypeSafe/Jev)** · Alternatives: add a TypeSafe key. Why: user decision. `.env.example` still lists `TYPESAFE_API_KEY=` because the course asks for it. Default model is decided in Phase 2 from evals. Revisit: Phase 2 results.

**D07 · 2026-10-07 · Verification sample: 20% of the pilot, 1% of the full run (seeded)** · Why: user decision; limits verifier cost on 660k rows while checking the pilot closely. Revisit: if the pilot error rate is high.

**D08 · 2026-10-07 · Dev 10k records are re-classified fresh inside the full run** · Alternatives: reuse dev results. Why: user decision; all graded labels come from one final configuration. Revisit: none.

**D09 · 2026-10-07 · Fallback (stronger) model may handle at most 2% of records** · Why: user decision; caps spend. Revisit: after measuring how many records need it.

**D10 · 2026-10-07 · Hosting: Supabase** · Why: user decision (for the live dashboard). Not used in Phase 1. Revisit: Phase 3 planning.

**D11 · 2026-10-07 · Downloads and catalog are folded into the nearest of the four business areas** · Why: user decision; the labels stay the contract's eight topics, and only the recommendation groups them. The exact mapping is written in Phase 2. Revisit: if a topic fits no area.

**D12 · 2026-10-07 · Sentiment tolerance predeclared as 0.5 (PENDING USER CONFIRMATION)** · The user wrote "±5". Sentiment ranges over [-1, 1], so ±5 would accept everything; we read it as ±0.5. Needs the user to confirm before any eval uses it. Revisit: on confirmation.

**D13 · 2026-10-07 · Golden 50: user supplies one label per field** · Why: user decision. We never fill in `golden_50_to_label.csv`, and its labels are never model inputs or prompt examples. Revisit: none.

**D14 · 2026-10-07 · Private repo `spotify-review-triage` for now; must be made public before submission** · Why: nothing is public until a secret/data scan of history passes. Revisit: before submission.

**D15 · 2026-10-07 · Phase 2 classifier comparison: small OpenAI model vs small Anthropic model (no Jev)** · Alternatives: Jev Choice/Score/Noul (needs a TypeSafe key the user does not hold). Why: user approved dropping Jev; both candidates run on development files only, never on the golden 50. Revisit: if a TypeSafe key becomes available.
