# v4 — real-retrieval gold-passage recall

arm: real retrieval (BM25)

query rule: v4 parameter name and unit only

BM25 searches the complete document store. The probe is used only as the post-retrieval evaluation label, never in the query or evidence selection.

items: 30; evidence shown to extractor: top 8 segments

| k | recall |
|---:|---:|
| 1 | 0.300 |
| 3 | 0.867 |
| 5 | 0.900 |
| 10 | 1.000 |
