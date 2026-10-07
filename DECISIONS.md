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

**D12 · 2026-10-07 · Sentiment tolerance predeclared as ±0.5, with ±0.25 also reported (CONFIRMED by user)** · Alternatives: 0 (exact), MAE only. Why: sentiment is a decimal in [-1, 1]; zero tolerance would mark near-identical values wrong. ±0.5 = same or adjacent step on a 5-step scale (-1, -0.5, 0, 0.5, 1); ±0.25 = same step. MAE is always reported too. Implemented in `spp/evaluate.py`. Revisit: none.

**D13 · 2026-10-07 · Golden 50: user supplies one label per field** · Why: user decision. We never fill in `golden_50_to_label.csv`, and its labels are never model inputs or prompt examples. Revisit: none.

**D14 · 2026-10-07 · Private repo `spotify-review-triage` for now; must be made public before submission** · Why: nothing is public until a secret/data scan of history passes. Revisit: before submission.

**D15 · 2026-10-07 · Phase 2 classifier comparison: small OpenAI model vs small Anthropic model (no Jev)** · Alternatives: Jev Choice/Score/Noul (needs a TypeSafe key the user does not hold). Why: user approved dropping Jev; both candidates run on development files only, never on the golden 50. Revisit: if a TypeSafe key becomes available.

**D16 · 2026-10-07 · Spend caps: $15 total for development and pilots; full-run cap set at Phase 4 (recommended $100)** · Why: user decision. Every paid command takes `--budget` and the shared ledger refuses any request whose worst-case cost would cross it. Revisit: Phase 3 measured costs.

**D17 · 2026-10-07 · Development reference set: 94 dev reviews labeled by the assistant, not by a human** · 80 drawn at random (seed `phase2-dev-v1`) from rows 500 to 4,999 of `analysis_10000.csv`, stratified by stars (40 one/two-star, 12 three-star, 28 four/five-star); 14 more chosen on purpose from rows 5,000+ to cover access, downloads and cancellation, which the random draw missed. Excludes every golden ID and text (a test enforces it). Why: comparing models needs a fixed answer key before the human golden labels exist; it is only used for tuning, and its agreement numbers are a consistency check, not accuracy. Revisit: never used as the final quality claim; the golden 50 is.

**D18 · 2026-10-07 · Model selection rule declared before any paid comparison** · Pick the cheapest configuration that is within 5 points of the best topic and intent agreement, has severity within ±1 on at least 85% of dev rows, and returns valid output for at least 98% of reviews on the first try. Why: decide the rule before seeing results so the choice is not tuned to the numbers. Revisit: if no configuration qualifies.

**D19 · 2026-10-07 · Candidates: GPT-6 Luna at effort none and low, Claude Haiku 4.5, and Claude Sonnet 5.5 at effort low as the fallback reference** · Alternatives: Jev (no TypeSafe key, D15); Sonnet 5 (course reference; Sonnet 5.5 is the current Sonnet at the same $2/$10 price). Why: two cheap primaries from the two providers we hold keys for, the lowest efforts first (the brief asks for the lowest thinking that passes evals), and one stronger model to see how much quality the cheap ones leave on the table. Only these four configurations are on the allowlist (`spp/providers.py`). Revisit: Phase 2 results.

**D20 · 2026-10-07 · Verifier uses a different prompt with no worked examples** · Why: the verifier should not inherit the enricher's examples or see its answers, so agreement means two independent readings matched. Revisit: if verifier agreement is too low to be useful.

**D21 · 2026-10-07 · Label rules added on top of the contract (all in `prompts/labels_v1.md`)** · (a) A control is `billing` only when the review says it is premium-only or paywalled; otherwise `usability` (or `catalog` for lyrics). (b) A boycott statement is `unclear` unless it also says the person is leaving or uninstalling, then `cancellation`. (c) Ads are `usability`, severity 2 unless they block use. (d) Hedged harm ("looks like I was hacked") stays below 5 and sets `needs_review`. (e) Entities are named products, plans, features, devices, apps, companies or places as written; never personal names. Why: these were the ambiguous cases in the dev sample; writing them down keeps the model, the verifier and the human labels consistent. Revisit: golden-eval disagreements.

**D22 · 2026-10-07 · Validation and retry policy** · Every returned item is checked for: an ID that was sent (unknown IDs ignored and logged), exactly one item per ID, contract enums, integer severity 1 to 5, finite sentiment in [-1, 1], a non-empty exact-substring quote, boolean `needs_review`. Invalid reviews are re-sent once (only the invalid ones); still invalid means quarantined with the reason and attempt count. Transport errors (429, 5xx, timeouts) get up to 4 attempts with exponential backoff and full jitter, capped at 30 s; a 400-type error is not retried. Revisit: Phase 3 failure rates.

**D23 · 2026-10-07 · Output-token caps per request** · 120 tokens per review plus 300 per request when the setting does not think (Luna none, Haiku), or plus 3,000 when it can (Luna low, Sonnet low). Why: a cap bounds the worst-case cost reserved before each call; measured output will set tighter caps in Phase 3. Revisit: Phase 3.

**D24 · 2026-10-07 · Business-area mapping for the memo** · access → access; usability and catalog → usability (finding, browsing and controlling music in the app); playback and downloads → playback (whether music actually plays, online or offline); billing and support → billing/support. Why: user asked to fold downloads and catalog into the nearest of the four areas. The 8 contract topics stay unchanged in every record; only the memo groups them. Revisit: if a large issue sits awkwardly in its area, the memo says so.

**D25 · 2026-10-07 · Rates file `cost/rates.csv` (dated 2026-10-07)** · GPT-6 Luna $0.10 input / $0.01 cached / $0.50 output per million, read from the OpenAI model page today. Claude rates from the Claude API reference table (cached 2026-09-25): Haiku 4.5 $1/$5, Sonnet 5.5 $2/$10, cache reads 0.1x. Input, cached input, cache writes and output are separate buckets; reasoning tokens are already inside output and are not added again. Revisit: re-check the Anthropic page before the pilot.
