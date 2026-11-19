# Recall vs corpus size (synthetic distractors)

Seed 20261119; BM25 config {'b': 0.5, 'k1': 1.5} (`configs/retrieval/lexical_config.json`).
Distractor documents re-use existing licence-evidenced text; no new
documents were fetched and no gold passage was duplicated.

| documents | segments | split | recall@1 | recall@3 | recall@5 | recall@10 |
|---:|---:|---|---:|---:|---:|---:|
| 4 | 121 | dev | 0.400 | 0.933 | 0.933 | 1.000 |
| 4 | 121 | test | 0.333 | 0.800 | 0.933 | 1.000 |
| 8 | 317 | dev | 0.333 | 0.600 | 0.933 | 1.000 |
| 8 | 317 | test | 0.267 | 0.533 | 0.867 | 0.933 |
| 10 | 357 | dev | 0.333 | 0.600 | 0.933 | 1.000 |
| 10 | 357 | test | 0.267 | 0.533 | 0.800 | 0.933 |
| 20 | 557 | dev | 0.333 | 0.533 | 0.733 | 1.000 |
| 20 | 557 | test | 0.200 | 0.400 | 0.533 | 0.933 |
| 40 | 957 | dev | 0.267 | 0.467 | 0.533 | 0.867 |
| 40 | 957 | test | 0.200 | 0.333 | 0.400 | 0.600 |

The v4 corpus is small and private; these numbers are not comparable
with v3. Recall on synthetic distractors is a stress test, not a claim
about any real four-/ten-paper corpus.
