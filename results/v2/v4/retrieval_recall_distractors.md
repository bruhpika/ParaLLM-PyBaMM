# v4 — real-retrieval recall: small vs full corpus (distractor stress)

arm: real retrieval (BM25)

query rule: v4 parameter name and unit only

The probe is used only as a post-retrieval evaluation label, never in the query or evidence selection. No model call is made.

items: 30; evidence shown to extractor: top 8 segments

- small corpus: 4 documents (private v4 store)
- full corpus: 10 documents (v4 store + all ingested papers and PyBaMM docs)

| k | small corpus | full corpus (distractors) |
|---:|---:|---:|
| 1 | 0.300 | 0.000 |
| 3 | 0.867 | 0.167 |
| 5 | 0.900 | 0.367 |
| 10 | 1.000 | 0.767 |

Small-corpus recall overstates retrieval quality: fewer distractors make the same query easier. The higher v4 numbers must be read with that in mind (no experimental claim).
