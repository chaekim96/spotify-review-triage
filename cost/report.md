# Cost and runtime calculator: 100-review pilot

Generated offline from `cost/usage.csv`, `cost/rates.csv` (dated rates, editable) and `cost/assumptions.json`. No key, no model call.
Input `cost_100.csv` sha256 `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e`; 100 IDs; 100 distinct texts.

## Measured (real pilot)

| run | stage | requests | failed | reviews sent | input tok | cached input tok | output tok | cost $ |
|---|---|---|---|---|---|---|---|---|
| pilot_cold | enrich | 4 | 0 | 102 | 5879 | 10816 | 7451 | 0.004422 |
| pilot_cold | verify | 1 | 0 | 20 | 3113 | 0 | 1522 | 0.010723 |
| pilot_cold | group | 3 | 0 | 36 | 3751 | 0 | 1412 | 0.001081 |
| pilot_cold | memo | 1 | 0 | 0 | 4335 | 0 | 1612 | 0.024790 |

**pilot_cold**: wall clock 98.52 s; stages {"enrich": 53.61, "group": 13.92, "memo": 15.44, "prepare": 0.06, "rank": 0.01, "verify": 15.49}; statuses {"completed": 100, "pending": 0, "quarantined": 0}; enrichment requests 4; result-cache hits 0; workers 1; batch size 50.

**pilot_warm**: wall clock 0.07 s; stages {"enrich": 0.0, "group": 0.0, "memo": 0.01, "prepare": 0.04, "rank": 0.0, "verify": 0.0}; statuses {"completed": 100, "pending": 0, "quarantined": 0}; enrichment requests 0; result-cache hits 100; workers 1; batch size 50.

Cold total $0.041016 ($0.4102 per 1,000 input rows, $0.000410 per record). Warm incremental $0.000000.
Models and settings: {"fallback": {"effort": "low", "model": "claude-sonnet-5-5"}, "group": {"effort": "low", "model": "gpt-6-luna"}, "memo": {"effort": "low", "model": "claude-sonnet-5-5"}, "primary": {"effort": "low", "model": "gpt-6-luna"}, "verify": {"effort": "default", "model": "claude-haiku-4-5-20251001"}}.

## Estimated (projections, not measurements)

Enrichment cost per distinct text 0.0000442 (measured, includes real retries/fallback); verification 1% of records; group calls 8 once; memo once; max concurrency 8; max fallback fraction 2%; output-token cap 120 per review.

| target | scenario | exact-text reuse | items sent | enrich $ | fallback $ | verify $ | group $ | memo $ | total $ | est. minutes | budget |
|---|---|---|---|---|---|---|---|---|---|---|---|
| scope_100k | base | yes | 78220 | 3.4585 | 0.0000 | 0.5362 | 0.0029 | 0.0248 | 4.02 | 87.4 | within ($10) |
| scope_100k | base | no | 100000 | 4.4216 | 0.0000 | 0.5362 | 0.0029 | 0.0248 | 4.99 | 111.7 | within ($10) |
| scope_100k | conservative | yes | 78220 | 5.1705 | 1.8773 | 0.6166 | 0.0029 | 0.0248 | 7.69 | 87.4 | within ($10) |
| scope_100k | conservative | no | 100000 | 6.6102 | 2.4000 | 0.6166 | 0.0029 | 0.0248 | 9.65 | 111.7 | within ($10) |
| full_660k | base | yes | 484189 | 21.4087 | 0.0000 | 3.5418 | 0.0029 | 0.0248 | 24.98 | 540.8 | within ($100) |
| full_660k | base | no | 660609 | 29.2092 | 0.0000 | 3.5418 | 0.0029 | 0.0248 | 32.78 | 737.8 | within ($100) |
| full_660k | conservative | yes | 484189 | 32.0060 | 11.6205 | 4.0731 | 0.0029 | 0.0248 | 47.73 | 540.8 | within ($100) |
| full_660k | conservative | no | 660609 | 43.6678 | 15.8546 | 4.0731 | 0.0029 | 0.0248 | 63.62 | 737.8 | within ($100) |

Local compute (laptop CPU, SQLite) is not billed and is not included above; its cost is unknown, not zero.
Formulas: item_cost = billed_units x usd_per_token (per-million price / 1,000,000); input, cached input, cache writes and output are separate buckets; reasoning tokens are already inside output.


## Measured at scale (real 100k run, `cost/full_run_measured.json`)

The 500 and 10,000 refreshes are read from the real run's call log as it passed those counts (not separate runs).

| distinct texts labeled by the model | enrichment cost $ | $ per 1,000 texts | succeeded requests | failed requests (rate-limit 429s, not billed) |
|---|---|---|---|---|
| 500 | 0.0217 | 0.0434 | 10 | 49 |
| 10,000 | 0.4410 | 0.0439 | 232 | 385 |
| 50,000 | 2.2207 | 0.0444 | 1,190 | 385 |
| 78,725 (final) | 3.8431 | 0.0488 (includes 199 Sonnet fallback texts) | 1,920 | 385 |

Full run, all roles: enrich $3.8431, verify $0.4250, group $0.0183, memo $0.0746, **total $4.3610** against a $10.00 cap.
Wall clock: initial phase 463 s (16 workers; hit the account's 10 requests/min and 60k tokens/min limits), resume 11,032 s (8 workers sharing a 9.5 requests/min limiter, about 7.8 requests/min).
The base-case projection for this scope ($4.03, with reuse) was within 8% of the measured $4.36.
