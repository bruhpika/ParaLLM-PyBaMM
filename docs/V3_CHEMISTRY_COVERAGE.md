# v3 multi-chemistry target coverage

This page records which chemistry families can be addressed by target specs in
v3, **which installed PyBaMM parameter sets back them**, and what is explicitly
unresolved. It is a software/applicability extension only: no electrochemical
parameter value was added, changed or fitted.

Version pin: **PyBaMM 26.8.0.0** (`pyproject.toml`). All facts below were
obtained by introspecting that installed version on 2026-11-27, never from
assumed parameter-set names.

## How the names were verified

The registry was enumerated directly:

```python
import pybamm
sorted(pybamm.parameter_sets)
```

Each set's raw dict (`pybamm.parameter_sets[name]`) exposes a `chemistry` field
and named OCP functions; `pybamm.ParameterValues(name)` exposes the loaded keys.
These are the only sources used for the classification below.

### All installed parameter sets (introspection result)

| Parameter set | `chemistry` field | Positive OCP function | Negative OCP / value |
|---|---|---|---|
| `Ai2020` | `lithium_ion` | `lico2_ocp_Ai2020` | `graphite_ocp_Enertech_Ai2020` |
| `Chayambuka2022` | `sodium_ion` | `NVPF_ocp_Chayambuka2022` | `HC_ocp_Chayambuka2022` |
| `Chen2020` | `lithium_ion` | `nmc_LGM50_ocp_Chen2020` | `graphite_LGM50_ocp_Chen2020` |
| `Chen2020_composite` | `lithium_ion` | `nmc_LGM50_ocp_Chen2020` | composite negative (no single OCP key) |
| `ECM_Example` | `ecm` | — | — |
| `Ecker2015` | `lithium_ion` | `nco_ocp_Ecker2015` | `graphite_ocp_Ecker2015` |
| `Ecker2015_graphite_halfcell` | `lithium_ion` | `graphite_ocp_Ecker2015` | `0.0` (Li metal) |
| `Marquis2019` | `lithium_ion` | `lico2_ocp_Dualfoil1998` | `graphite_mcmb2528_ocp_Dualfoil1998` |
| `MSMR_Example` | `lithium_ion` | — (MSMR functions) | — |
| `Mohtat2020` | `lithium_ion` | `NMC_ocp_PeymanMPM` | `graphite_ocp_PeymanMPM` |
| `NCA_Kim2011` | `lithium_ion` | `nca_ocp_Kim2011` | `graphite_ocp_Kim2011` |
| `OKane2022` | `lithium_ion` | `nmc_LGM50_ocp_Chen2020` | `graphite_LGM50_ocp_Chen2020` |
| `OKane2022_graphite_SiOx_halfcell` | `lithium_ion` | `graphite_LGM50_ocp_Chen2020` | `0.0` (Li metal) |
| `ORegan2022` | `lithium_ion` | `nmc_LGM50_ocp_Chen2020` | `graphite_LGM50_ocp_Chen2020` |
| `Prada2013` | `lithium_ion` | `LFP_ocp_Afshar2017` | `graphite_LGM50_ocp_Chen2020` |
| `Ramadass2004` | `lithium_ion` | `lico2_ocp_Ramadass2004` | `graphite_ocp_Ramadass2004` |
| `Sulzer2019` | `lead_acid` | — | — |
| `Xu2019` | `lithium_ion` | `nmc_ocp_Xu2019` | `0.0` (Li metal) |

The `chemistry` field alone is not sufficient to classify chemistry: every
lithium-metal half-cell above still reports `lithium_ion`. The electrode OCP
functions and parameter keys were therefore inspected as well.

## v3 target specs

| Target id | Chemistry | Parameter set | Model / options | Config |
|---|---|---|---|---|
| `lfp_graphite_prada2013` | LFP / graphite | `Prada2013` | `DFN`, default options | `configs/v3/target_lfp_graphite_prada2013.yaml` |
| `nmc811_lgm50_oregan2022` | NMC811 / graphite | `ORegan2022` | `DFN`, default options | `configs/v3/target_nmc811_lgm50_oregan2022.yaml` |
| `limetal_nmc_xu2019` | Li-metal / NMC | `Xu2019` | `DFN`, `{"working electrode": "positive"}` | `configs/v3/target_limetal_nmc_xu2019.yaml` |

`configs/v2/target_lgm50.yaml` is unchanged and remains the v0.2 demonstrator
(`Chen2020`, default options). The `configs/v3/chemistry_coverage.meta.yaml`
file is an auxiliary, declarative coverage/unresolved record; it is not a
target spec and is excluded from catalog loading.

### Evidence per chemistry

- **LFP / graphite — `Prada2013`.** `get_parameter_values` documents
  "Parameters for an LFP cell"; the positive OCP is `LFP_ocp_Afshar2017` and
  the negative OCP is a graphite fit. Electrolyte documented as "LiPF6 in
  EC:EMC (3:7)" (`electrolyte_conductivity_Prada2013` docstring).
- **NMC811 — `ORegan2022`.** There is **no installed set named `NMC811`**. The
  designation is documented inside the installed source:
  `nmc_LGM50_entropic_change_ORegan2022` says "LG M50 NMC 811 entropic change
  in open-circuit potential (OCP)". Its positive OCP is the same
  `nmc_LGM50_ocp_Chen2020` fit used by `Chen2020` and `OKane2022`. The target
  records `nmc_composition: "811"` so the rubric can downgrade NMC111 evidence
  without blocking the NMC family.
- **Li-metal — `Xu2019`.** The negative electrode OCP is `0.0`, the set defines
  `Lithium metal partial molar volume [m3.mol-1]` and
  `Exchange-current density for lithium metal electrode [A.m-2]`, and has no
  graphite negative-electrode parameters. The paper named in the source is
  "Evolution of Dead Lithium Growth in Lithium Metal Batteries". Verified by
  simulation: the default `working electrode: both` option fails on this set
  (missing negative-electrode parameters), while the declared
  `working electrode: positive` half-cell option succeeds.

## Applicability support added

- `TargetSpecification` gained explicit, defaulted fields: `model_options`,
  `nmc_composition` and introspection-derived `verification` provenance. All
  existing construction sites keep working with their previous arguments.
- `load_target` parses the new fields; `specifications.load_target_catalog`
  loads all v3 target specs deterministically and rejects duplicate ids,
  unknown chemistry-family labels, unknown model names and malformed
  composition labels. Catalog loading performs **no** PyBaMM calls.
- Rubric chemistry scoring now reads the target composition from the explicit
  `nmc_composition` field, so NMC811 vs NMC111 is a scored (non-blocking)
  distinction instead of being invisible.
- `pybamm_engine` exposes `parameter_set_chemistry`, `parameter_set_ocp_names`
  and `validate_model_options` so callers and tests inspect PyBaMM through the
  single sanctioned module.

## Scientific limitations and assumptions

1. A verified parameter set does **not** make a chemistry experimentally
   validated. These specs declare applicability of literature parameters only.
2. No parameter value, unit, model option or solver was invented: all names
   come from introspection of PyBaMM 26.8.0.0; all option validity is checked
   by PyBaMM itself at model-build time.
3. `Prada2013` does not provide a graphite OCP; PyBaMM substitutes the Chen2020
   LG M50 fit. This is a property of the installed set and is recorded as a
   caveat, not silently repaired.
4. `Xu2019`'s source docstring contains an inconsistent copy-paste sentence
   ("graphite anode, LCO cathode") that contradicts its own parameter dict.
   The dict (NMC positive, Li-metal negative) is treated as authoritative and
   the discrepancy is recorded, not guessed away.
5. The NMC811 label is attached to the **documented LG M50 cell**, not to a
   stoichiometry measured or re-derived here. Do not read it as an independent
   composition calibration.
6. Cell format and state of charge are left unset in the v3 specs where the
   installed set does not declare them. Unknown facts score neutrally in the
   rubric; they are never defaulted to a favourable value.
7. Integration tests run short deterministic discharges; they prove the set
   loads and the options are accepted, **not** parameter identifiability or
   experimental transferability.
8. Never use calibration data as independent validation data; none is present
   in this extension.

## Unresolved

- **A parameter set literally named `NMC811`: UNRESOLVED.** No such set exists
  in PyBaMM 26.8.0.0. NMC811 is supported only via the documented LG M50 set
  (`ORegan2022`). No set was fabricated.
- **LMO target: UNRESOLVED.** The lexicon recognises the LMO family, but no LMO
  parameter set is installed. No LMO target spec was added.
- Other lexicon families (NCA, LCO) have installed sets (`NCA_Kim2011`,
  `Ai2020`/`Marquis2019`/`Ramadass2004`) but were outside the assigned v3 scope
  and were not added as target specs. Sodium-ion (`Chayambuka2022`) and lead-acid
  (`Sulzer2019`) sets are installed but the engine's model family is still
  pinned to `lithium_ion`, so they are not addressable in v3.

## Reproduce

```bash
.venv/bin/python -m pytest -q -m "not benchmark and not characterization"
.venv/bin/python -m ruff check .
```
