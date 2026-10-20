# Phase 2 classifier comparison (development records)

Run started 2026-10-20T08:32:32Z; 94 dev reviews; batch size 47; 1 worker; budget cap $2.0.
Reference: evals/dev_reference_v1.jsonl (assistant-labeled dev rows, not golden). Agreement is measured against assistant labels, so it is a consistency check, not human accuracy.
Measured values come from saved provider usage. Full-run figures are estimates (cost per review x row count).

| config | model | topic | intent | sev exact | sev ±1 | sev MAE | sent MAE | sent ±0.5 | sent ±0.25 | needs_review | 1st-pass valid | quarantined | cost $ | sec | est. full $ (no reuse / reuse) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| luna-none | gpt-6-luna | 0.0 | 0.0 | 0.0 | 0.0 | None | None | 0.0 | 0.0 | 0.0 | 0.0 | 94 | 0.0 | 46.77 | 0.0 / 0.0 |
| luna-low | gpt-6-luna | 0.0 | 0.0 | 0.0 | 0.0 | None | None | 0.0 | 0.0 | 0.0 | 0.0 | 94 | 0.0 | 49.33 | 0.0 / 0.0 |
| haiku | claude-haiku-4-5-20251001 | 0.766 | 0.9362 | 0.7447 | 0.9681 | 0.25 | 0.1185 | 0.9574 | 0.8511 | 0.8511 | 0.9681 | 2 | 0.058948 | 79.93 | 414.27 / 303.64 |
| sonnet-low | claude-sonnet-5-5 | 0.8617 | 1.0 | 0.883 | 0.9894 | 0.1277 | 0.0766 | 1.0 | 0.9255 | 0.8511 | 1.0 | 0 | 0.131896 | 63.48 | 926.93 / 679.39 |

## Pairwise agreement between configurations

| pair | n | topic | intent | severity | sentiment MAE |
|---|---|---|---|---|---|
| haiku~sonnet-low | 92 | 0.8043 | 0.9565 | 0.8152 | 0.1163 |

## Selection

Rule (declared before the run): {"agreement_margin": 0.05, "severity_within_1_min": 0.85, "first_pass_valid_min": 0.98}
Result: {"config": "sonnet-low", "eligible": ["sonnet-low"], "why": "cheapest configuration meeting the declared rule"}

