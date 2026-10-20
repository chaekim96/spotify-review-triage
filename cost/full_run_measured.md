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
