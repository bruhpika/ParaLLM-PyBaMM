# Segment-length preflight (no silent truncation)

Model `sentence-transformers/all-MiniLM-L6-v2` revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`; max sequence length 256 (budget 254 after CLS/SEP).
Handling: over-length segments are split into token windows and their embeddings pooled; no silent truncation.

| corpus | segments | over-length | fraction | longest tokens |
|---|---:|---:|---:|---:|
| v3/full | 196 | 48 | 0.245 | 2445 |
| v4/small | 121 | 58 | 0.479 | 2450 |
| v4/full | 317 | 106 | 0.334 | 2450 |
