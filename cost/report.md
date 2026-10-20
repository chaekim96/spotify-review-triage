# Cost and runtime calculator: 100-review pilot

Generated offline from `cost/usage.csv`, `cost/rates.csv` (dated rates, editable) and `cost/assumptions.json`. No key, no model call.
Input `cost_100.csv` sha256 `c884ac3b9be5066995d5063f96ad9af6e5e082975788c1684c4f6b6ea661dd0e`; 100 IDs; 100 distinct texts.

## Measured (real pilot)

| run | stage | requests | failed | reviews sent | input tok | cached input tok | output tok | cost $ |
|---|---|---|---|---|---|---|---|---|
| pilot_cold | enrich | 3 | 0 | 101 | 5793 | 8112 | 7546 | 0.004433 |
| pilot_cold | verify | 1 | 0 | 20 | 3113 | 0 | 1498 | 0.010603 |
| pilot_cold | group | 3 | 0 | 37 | 3657 | 0 | 1571 | 0.001151 |
| pilot_cold | memo | 1 | 0 | 0 | 4347 | 0 | 1669 | 0.025384 |
| pilot_warm | memo | 1 | 0 | 0 | 3413 | 0 | 1537 | 0.022196 |

**pilot_cold**: wall clock 112.89 s; stages {"enrich": 65.51, "group": 17.75, "memo": 12.96, "prepare": 0.05, "rank": 0.01, "verify": 16.6}; statuses {"completed": 100, "pending": 0, "quarantined": 0}; enrichment requests 3; result-cache hits 0; workers 1; batch size 50.

**pilot_warm**: wall clock 12.23 s; stages {"enrich": 0.0, "group": 0.0, "memo": 12.14, "prepare": 0.07, "rank": 0.0, "verify": 0.0}; statuses {"completed": 100, "pending": 0, "quarantined": 0}; enrichment requests 0; result-cache hits 100; workers 1; batch size 50.

Cold total $0.041572 ($0.4157 per 1,000 input rows, $0.000416 per record). Warm incremental $0.022196.
Models and settings: {"fallback": {"effort": "low", "model": "claude-sonnet-5-5"}, "group": {"effort": "low", "model": "gpt-6-luna"}, "memo": {"effort": "low", "model": "claude-sonnet-5-5"}, "primary": {"effort": "low", "model": "gpt-6-luna"}, "verify": {"effort": "default", "model": "claude-haiku-4-5-20251001"}}.

## Estimated (projections, not measurements)

Enrichment cost per distinct text 0.0000443 (measured, includes real retries/fallback); verification 1% of records; group calls 8 once; memo once; max concurrency 8; max fallback fraction 2%; output-token cap 120 per review.

| target | scenario | exact-text reuse | items sent | enrich $ | fallback $ | verify $ | group $ | memo $ | total $ | est. minutes | budget |
|---|---|---|---|---|---|---|---|---|---|---|---|
| scope_100k | base | yes | 78220 | 3.4678 | 0.0000 | 0.5302 | 0.0031 | 0.0254 | 4.03 | 106.8 | within ($10) |
| scope_100k | base | no | 100000 | 4.4334 | 0.0000 | 0.5302 | 0.0031 | 0.0254 | 4.99 | 136.5 | within ($10) |
| scope_100k | conservative | yes | 78220 | 5.1844 | 1.8773 | 0.6097 | 0.0031 | 0.0254 | 7.70 | 106.8 | within ($10) |
| scope_100k | conservative | no | 100000 | 6.6280 | 2.4000 | 0.6097 | 0.0031 | 0.0254 | 9.67 | 136.5 | within ($10) |
| full_660k | base | yes | 484189 | 21.4661 | 0.0000 | 3.5022 | 0.0031 | 0.0254 | 25.00 | 660.8 | within ($100) |
| full_660k | base | no | 660609 | 29.2876 | 0.0000 | 3.5022 | 0.0031 | 0.0254 | 32.82 | 901.6 | within ($100) |
| full_660k | conservative | yes | 484189 | 32.0919 | 11.6205 | 4.0275 | 0.0031 | 0.0254 | 47.77 | 660.8 | within ($100) |
| full_660k | conservative | no | 660609 | 43.7849 | 15.8546 | 4.0275 | 0.0031 | 0.0254 | 63.70 | 901.6 | within ($100) |

Local compute (laptop CPU, SQLite) is not billed and is not included above; its cost is unknown, not zero.
Formulas: item_cost = billed_units x usd_per_token (per-million price / 1,000,000); input, cached input, cache writes and output are separate buckets; reasoning tokens are already inside output.

