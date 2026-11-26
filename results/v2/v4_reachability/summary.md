# Private v4 — evidence reachability (diagnostic)

split: `all` (seed 20261119); evidence from `data/private_v4/results/raw_v25_r0.jsonl`; no model calls.

Reachable gold fields: **177/210** = **0.843** (upper bound for condition-field accuracy).

| field | reachable / total | ceiling |
| --- | ---: | ---: |
| chemistry | 30 / 30 | 1.000 |
| cell | 10 / 30 | 0.333 |
| format | 27 / 30 | 0.900 |
| temperature_k | 23 / 30 | 0.767 |
| soc | 30 / 30 | 1.000 |
| method | 30 / 30 | 1.000 |
| protocol | 27 / 30 | 0.900 |

Per-item unreachable fields stay private: `data/private_v4/results/reachability_detail.json`.
