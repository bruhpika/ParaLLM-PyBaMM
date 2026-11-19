# Dense / hybrid retrieval (optional extra)

Model: `sentence-transformers/all-MiniLM-L6-v2` (90868376 bytes, licence apache-2.0), revision `1110a243fdf4706b3f48f1d95db1a4f5529b4d41`.
BM25 leg uses the tuned config {'b': 0.5, 'k1': 1.5} from `configs/retrieval/lexical_config.json`.
No model weights are bundled; embedding cache is gitignored.

## bm25

- v3/full dev: recall@1/3/5/10 0.167/0.222/0.222/0.333
- v4/small dev: recall@1/3/5/10 0.400/0.933/0.933/1.000
- v4/full dev: recall@1/3/5/10 0.333/0.600/0.933/1.000

## dense

- v3/full dev: recall@1/3/5/10 0.111/0.222/0.333/0.389
- v4/small dev: recall@1/3/5/10 0.200/0.533/0.667/0.867
- v4/full dev: recall@1/3/5/10 0.133/0.267/0.467/0.600

## hybrid

- v3/full dev: recall@1/3/5/10 0.167/0.222/0.278/0.389
- v4/small dev: recall@1/3/5/10 0.333/0.667/0.933/1.000
- v4/full dev: recall@1/3/5/10 0.400/0.533/0.733/1.000

The v4 corpus is small and private; v3 and v4 are not comparable.
