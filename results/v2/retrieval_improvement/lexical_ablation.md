# Lexical retrieval ablation (dev-only tuning)

Seed 20261119; configurations tried: 11 (`config_log.jsonl` includes failures).
Gold labels are post-retrieval audit labels only. No model call is made.

| configuration | dev recall@1 | dev MRR | dev doc-recall@10 |
|---|---:|---:|---:|
| bm25 baseline (k1=1.5,b=0.75) | 0.333 | 0.556 | 1.000 |
| bm25_b_0p5 | 0.400 | 0.611 | 1.000 |
| bm25_b_0p9 | 0.200 | 0.483 | 1.000 |
| bm25_k1_1p2 | 0.333 | 0.556 | 1.000 |
| bm25_k1_2p0 | 0.333 | 0.558 | 1.000 |
| boost_tables | 0.133 | 0.400 | 1.000 |
| boost_units | 0.333 | 0.556 | 1.000 |
| query_all | 0.200 | 0.453 | 1.000 |
| query_all_and_boosts | 0.200 | 0.334 | 0.933 |
| registry_aliases | 0.400 | 0.575 | 1.000 |
| symbols | 0.267 | 0.500 | 1.000 |
| unit_terms | 0.333 | 0.556 | 1.000 |

Chosen on dev: **bm25_b_0p5** (primary recall@1, then MRR and doc-recall@10).
Test was evaluated once for this configuration:

| benchmark / corpus | test recall@1/3/5/10 | test MRR | test doc-recall@10 |
|---|---:|---:|---:|
| v3/full | 0.158/0.263/0.368/0.421 | 0.225 | 0.526 |
| v4/full | 0.267/0.533/0.867/0.933 | 0.442 | 0.933 |
| v4/small | 0.333/0.800/0.933/1.000 | 0.552 | 1.000 |

Test comparison with the unchanged BM25 baseline (same frozen split):

| benchmark / corpus | baseline recall@1/3/5/10 | chosen recall@1/3/5/10 |
|---|---:|---:|
| v3/full | 0.158/0.211/0.316/0.421 | 0.158/0.263/0.368/0.421 |
| v4/full | 0.200/0.333/0.600/0.933 | 0.267/0.533/0.867/0.933 |
| v4/small | 0.267/0.800/0.867/1.000 | 0.333/0.800/0.933/1.000 |

The v4 corpus is small and private; v3 and v4 results are not comparable.
