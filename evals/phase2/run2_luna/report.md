# Phase 2 classifier comparison (development records)

Run started 2026-10-20T08:50:02Z; 94 dev reviews; batch size 47; 1 worker; budget cap $0.5.
Reference: evals/dev_reference_v1.jsonl (assistant-labeled dev rows, not golden). Agreement is measured against assistant labels, so it is a consistency check, not human accuracy.
Measured values come from saved provider usage. Full-run figures are estimates (cost per review x row count).

| config | model | topic | intent | sev exact | sev ±1 | sev MAE | sent MAE | sent ±0.5 | sent ±0.25 | needs_review | 1st-pass valid | quarantined | cost $ | sec | est. full $ (no reuse / reuse) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| luna-none | gpt-6-luna | 0.8404 | 0.9787 | 0.9043 | 0.9787 | 0.1277 | 0.1117 | 0.9681 | 0.8511 | 0.8936 | 1.0 | 0 | 0.004261 | 38.67 | 29.94 / 21.95 |
| luna-low | gpt-6-luna | 0.9255 | 0.9787 | 0.8936 | 0.9787 | 0.1383 | 0.1138 | 0.9787 | 0.8617 | 0.8936 | 0.9894 | 0 | 0.004304 | 51.01 | 30.25 / 22.17 |

## Pairwise agreement between configurations

| pair | n | topic | intent | severity | sentiment MAE |
|---|---|---|---|---|---|
| luna-none~luna-low | 94 | 0.8723 | 0.9787 | 0.9468 | 0.0532 |

## Selection

Rule (declared before the run): {"agreement_margin": 0.05, "severity_within_1_min": 0.85, "first_pass_valid_min": 0.98}
Result: {"config": "luna-low", "eligible": ["luna-low"], "why": "cheapest configuration meeting the declared rule"}

