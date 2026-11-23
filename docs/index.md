# PARALLM

LLM-assisted, provenance-grounded parameterization for PyBaMM.

PARALLM's unit of work is the **per-parameter dossier**: literature evidence ->
applicability/conflict assembly -> dossier with a mandatory human approval gate
-> observability-based CALIBRATE/FIX/MEASURE decisions. The LLM reads evidence
and proposes; it never decides values.

## Start here

<div class="pl-card-grid">
  <a class="pl-card" href="QUICKSTART/">
    <span class="pl-card__label">Quickstart</span>
    <span class="pl-card__hint">First end-to-end run</span>
  </a>
  <a class="pl-card" href="INSTALLATION/">
    <span class="pl-card__label">Installation</span>
    <span class="pl-card__hint">Environment and dependencies</span>
  </a>
  <a class="pl-card" href="CLI/">
    <span class="pl-card__label">CLI guide</span>
    <span class="pl-card__hint">Commands, statuses and error codes</span>
  </a>
  <a class="pl-card" href="BENCHMARK_RESULTS/">
    <span class="pl-card__label">Benchmark results</span>
    <span class="pl-card__hint">Committed scientific results</span>
  </a>
</div>

## Scientific stance

!!! note "Scientific stance"
    Every number in the results sections comes from a committed file under
    `results/`. Synthetic recovery is not experimental validation; a successful
    optimization is not parameter identifiability. See
    [Scientific limitations](SCIENTIFIC_LIMITATIONS.md).

<div class="pl-next">next: parallm doctor</div>
