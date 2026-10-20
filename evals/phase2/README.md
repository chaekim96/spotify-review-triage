# Phase 2 model comparison (development records)

94 development reviews (`evals/dev_reference_v1.jsonl`, assistant-labeled, never the golden 50); batches of 47; 1 worker.
Agreement is with assistant reference labels, so it is a consistency check, not human accuracy.

| config | model | topic | intent | severity exact | severity ±1 | sentiment ±0.5 | sentiment ±0.25 | valid on 1st try | measured cost $ | source |
|---|---|---|---|---|---|---|---|---|---|---|
| luna-none | gpt-6-luna, effort none | 0.840 | 0.979 | 0.904 | 0.979 | 0.968 | 0.851 | 1.000 | 0.0043 | run2_luna |
| **luna-low** | gpt-6-luna, effort low | **0.926** | 0.979 | 0.894 | 0.979 | 0.979 | 0.862 | 0.989 | 0.0043 | run2_luna |
| haiku | claude-haiku-4-5-20251001 | 0.766 | 0.936 | 0.745 | 0.968 | 0.957 | 0.851 | 0.968 | 0.0589 | run1 |
| sonnet-low | claude-sonnet-5-5, effort low | 0.862 | 1.000 | 0.883 | 0.989 | 1.000 | 0.926 | 1.000 | 0.1319 | run1 |

Selection rule declared before any paid call (DECISIONS D18): cheapest configuration within 5 points of the best topic and intent
agreement, severity ±1 on at least 85%, and at least 98% valid on the first try. Across all four: best topic 0.926 (luna-low),
best intent 1.000 (sonnet-low). Only **luna-low** qualifies (sonnet-low misses the topic margin; luna-none and haiku miss the topic margin).
It is also about 30x cheaper than Sonnet 5.5 and about 14x cheaper than Haiku 4.5 per review here.

In `run1` the two Luna rows failed because the OpenAI account had no credit (HTTP 429 `insufficient_quota`, no charge);
they were rerun in `run2_luna` after credit was added. All failed attempts stay in `run1/calls.jsonl`.
