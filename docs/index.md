# PARALLM

**PARALLM** is a research framework for parameterizing physics-based
lithium-ion battery models built on PyBaMM. Its unit of work is the
**per-parameter dossier**: literature evidence -> applicability/conflict
assembly -> dossier with a mandatory human approval gate ->
observability-based CALIBRATE/FIX/MEASURE decisions.

This site documents the scientific scope, architecture, benchmarks and
limitations. The LLM reads evidence and proposes; it never decides values.

## Start here

- [Quickstart](QUICKSTART.md)
- [Installation](INSTALLATION.md)
- [Examples gallery](examples.md)
- [Benchmark results](BENCHMARK_RESULTS.md)
- [Scientific limitations](SCIENTIFIC_LIMITATIONS.md)

## Repository

- [GitHub repository](https://github.com/bruhpika/ParaLLM-PyBaMM)
- [Issue tracker](https://github.com/bruhpika/ParaLLM-PyBaMM/issues)

## Scientific stance

Every number in the results sections comes from a committed file under
`results/`. Synthetic recovery is not experimental validation; a successful
optimization is not parameter identifiability. See
[Scientific limitations](SCIENTIFIC_LIMITATIONS.md).
