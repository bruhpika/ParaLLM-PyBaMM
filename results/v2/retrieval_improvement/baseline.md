# BM25 retrieval baseline — frozen dev/test protocol

Seed: 20261119 (split `configs/retrieval/dev_test_split.json`).
Configurations logged so far: 6 (`config_log.jsonl`, failures included).
Tuning is dev-only; test is reported once per configuration family.
Gold labels are frozen post-retrieval audit labels; no probe or gold
information enters the query, expansion, boosts or configuration choice.

## v3 / full

index: 4 documents, 196 segments; gold retrievable: dev 11/18, test 11/19

| metric | dev mean [95% CI] | test mean [95% CI] |
|---|---:|---:|
| recall@1 | 0.167 [0.000, 0.333] | 0.158 [0.000, 0.316] |
| recall@3 | 0.222 [0.056, 0.444] | 0.211 [0.053, 0.421] |
| recall@5 | 0.222 [0.056, 0.444] | 0.316 [0.105, 0.526] |
| recall@10 | 0.333 [0.111, 0.556] | 0.421 [0.211, 0.632] |
| mrr | 0.198 [0.046, 0.377] | 0.223 [0.078, 0.397] |
| document_recall@1 | 0.333 [0.111, 0.556] | 0.263 [0.105, 0.474] |
| document_recall@3 | 0.444 [0.222, 0.667] | 0.368 [0.158, 0.579] |
| document_recall@5 | 0.500 [0.278, 0.722] | 0.474 [0.263, 0.684] |
| document_recall@10 | 0.556 [0.333, 0.778] | 0.526 [0.316, 0.737] |

## v4 / small

index: 4 documents, 121 segments; gold retrievable: dev 15/15, test 15/15

| metric | dev mean [95% CI] | test mean [95% CI] |
|---|---:|---:|
| recall@1 | 0.333 [0.133, 0.600] | 0.267 [0.067, 0.533] |
| recall@3 | 0.933 [0.800, 1.000] | 0.800 [0.600, 1.000] |
| recall@5 | 0.933 [0.800, 1.000] | 0.867 [0.667, 1.000] |
| recall@10 | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |
| mrr | 0.556 [0.400, 0.722] | 0.502 [0.358, 0.669] |
| document_recall@1 | 0.733 [0.467, 0.933] | 0.467 [0.200, 0.733] |
| document_recall@3 | 1.000 [1.000, 1.000] | 0.933 [0.800, 1.000] |
| document_recall@5 | 1.000 [1.000, 1.000] | 0.933 [0.800, 1.000] |
| document_recall@10 | 1.000 [1.000, 1.000] | 1.000 [1.000, 1.000] |

## v4 / full

index: 8 documents, 317 segments; gold retrievable: dev 15/15, test 15/15

| metric | dev mean [95% CI] | test mean [95% CI] |
|---|---:|---:|
| recall@1 | 0.200 [0.000, 0.400] | 0.200 [0.000, 0.400] |
| recall@3 | 0.400 [0.198, 0.667] | 0.333 [0.133, 0.600] |
| recall@5 | 0.867 [0.667, 1.000] | 0.600 [0.333, 0.867] |
| recall@10 | 1.000 [1.000, 1.000] | 0.933 [0.800, 1.000] |
| mrr | 0.421 [0.274, 0.595] | 0.359 [0.205, 0.544] |
| document_recall@1 | 0.467 [0.200, 0.733] | 0.333 [0.133, 0.600] |
| document_recall@3 | 0.800 [0.600, 1.000] | 0.733 [0.467, 0.933] |
| document_recall@5 | 0.933 [0.800, 1.000] | 0.733 [0.467, 0.933] |
| document_recall@10 | 1.000 [1.000, 1.000] | 0.933 [0.800, 1.000] |

## Caveats

- Current local stores hold 4 documents for v3 and 8 for the v4 full corpus after the Chen2020 article text and supplement were untracked. The committed v3/v4 recall figures were produced with 6 and 10 documents; the re-measured numbers here describe the current local corpus and are not directly comparable with them.
- The v4 corpus is small and private; v3 and v4 numbers are **not comparable**.
- Item-level v4 rows stay private; this file reports aggregates only.
- Query mismatches vs the frozen audits and unretrievable gold labels are
  counted above; they are not silently dropped.
