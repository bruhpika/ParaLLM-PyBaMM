# v4 offline side-by-side (clarified label, split metrics)

Oracle label: **oracle-located (probe window; NOT a performance upper bound)**.
It locates the gold passage from the fixture probe, but its evidence
block is a small probe window rather than the 8-segment BM25 block.
The arms are therefore **not comparable as an upper-bound vs lower-bound
pair**, and oracle value accuracy must not be read as a ceiling.

## Evidence volume handed to the extractor

| arm | items | mean chars | median chars | min | max |
|---|---:|---:|---:|---:|---:|
| oracle compact | 30 | 561 | 564 | 527 | 598 |
| BM25 baseline | 30 | 43371 | 44298 | 28196 | 55374 |
| BM25 tuned (b=0.5) | 30 | 45640 | 44611 | 28196 | 54678 |

BM25 arms show ~81x more evidence text than the oracle window (8 segments).

## dev split (n=15)

| arm | value found | condition accuracy | invented-condition rate | abstention |
|---|---:|---:|---:|---:|
| oracle compact | 0.200 | 0.181 | 0.133 | 0.400 |
| BM25 baseline | 0.400 | 0.257 | 0.000 | 0.000 |
| BM25 tuned (b=0.5) | 0.533 | 0.257 | 0.000 | 0.000 |

## test split (n=15)

| arm | value found | condition accuracy | invented-condition rate | abstention |
|---|---:|---:|---:|---:|
| oracle compact | 0.333 | 0.190 | 0.133 | 0.267 |
| BM25 baseline | 0.733 | 0.248 | 0.000 | 0.000 |
| BM25 tuned (b=0.5) | 0.733 | 0.257 | 0.000 | 0.000 |

Private per-item rows stay under `data/private_v4/results/`; the v4
corpus is small and private and is not comparable with v3.
