# v3 — real-retrieval gold-passage recall

arm: real retrieval (BM25)

query rule: v3 RetrievalFacets (parameter names, materials, cell, conditions, techniques)

BM25 searches the complete document store. The probe is used only as the post-retrieval evaluation label, never in the query or evidence selection.

items: 37; evidence shown to extractor: top 8 segments

| k | recall |
|---:|---:|
| 1 | 0.189 |
| 3 | 0.351 |
| 5 | 0.459 |
| 10 | 0.486 |
