# Cost and runtime calculator

Offline replay (default, no key, no model call) recomputes the measured pilot and every projection from saved files:

```sh
uv run python -m spp cost            # = cost replay; writes cost/report.md
```

Explicit pilot execution (paid, needs keys in `.env`; runs `cost_100.csv` cold with empty caches and 1 worker through
enrich, 20% verification, group, rank and memo, then warm with the saved result cache):

```sh
uv run python -m spp cost pilot --confirm --budget 1
```

Files:
- `rates.csv`: dated, editable prices per million tokens with source links. Input, cached input, cache write and output are separate buckets; reasoning tokens are already inside output.
- `usage.csv`: one row per real call (cold and warm), mapped to `pilot_calls.jsonl` by `run_id` + `request_id`.
- `pilot_calls.jsonl`: every attempt with stage, model, settings, usage, timing and outcome. No keys.
- `pilot_records.jsonl`: one result/status per pilot ID with the contract row hash and labels (separate from `grading/records.jsonl`).
- `pilot_summary.json`: measured wall-clock and per-stage seconds, statuses, cache hits.
- `assumptions.json`: editable projection inputs (budget, targets, concurrency, fallback cap, scenarios). Changing them never changes the measured pilot.
- `report.md`: the measured table and the base/conservative, reuse/no-reuse projections with over-budget warnings.

Local compute (laptop, SQLite) is not billed and is reported as unknown, not zero.
