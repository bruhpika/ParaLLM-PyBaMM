# Decision package: action for `Negative particle diffusivity [m2.s-1]`

**Status: owner decision taken (2026-11-27) — option C, conditional
`CALIBRATE`.** The dossier action is unchanged (`MEASURE`) until the gates at
the end of this document are recorded (AGENTS.md rule 10). All numbers below
are **SYNTHETIC**, local, finite-difference FIM diagnostics on model-generated
curves; none is experimental evidence.

## Question

Should `neg_particle_diffusivity` stay **`MEASURE`** (its current action), or
should the recorded observability assessment be extended so that the
deterministic join upgrades it to **`CALIBRATE`**?

## Evidence chain (all committed, all synthetic)

| step | artifact | result |
|---|---|---|
| voltage-only baseline (P2, committed) | `results/p2/diffusivity_feasibility/report.json` | mean \|S\| 0.011 / 0.021 / 0.048 at 0.5C/1C/2C → `UNOBSERVABLE` → `MEASURE` |
| observable-augmented study (2026-11-27, corrected) | `results/observables/diffusivity_multi_observable_fim.{json,md}` | low-SOC GITT pulse drop 0.082, sqrt(t) slope 0.100 clear the 0.05 bar; combined FIM 9.029e4 → 1.796e5; verdict flips to `OBSERVABLE` under the declared conjunction |
| protocol correction | same artifact + `CHANGELOG.md` | the first run used the PyBaMM default 100 % SOC where the graphite OCP is flat; its null was a protocol artefact. Committed protocol: 20 % SOC, 0.2C, 120 s pulse / 180 s rest × 5 |
| joint collinearity check (2026-11-27) | `results/observables/joint_diffusivity_fim.{json,md}` | `D_neg`, `j0_neg`, `D_e` free together: marginal rel. SE 0.263 % (single-parameter 0.236 %, variance inflation **1.25**), correlations 0.153 / −0.444, survives the declared 0.9 warning; stable across 0.5–5 % FD steps |
| measurement specification | `docs/EXPERIMENTAL_DATA_REQUIREMENTS.md` §2.7 | what an experimental GITT dataset must contain |

The committed voltage-only baseline is reproduced **exactly** (Δ = 0.0 at all
three rates), so the comparison is not a solver artefact. EIS is verified blind
to solid diffusivity in PyBaMM 26.8.0.0 (positive control ~0.37 from kinetics
vs ~8e-5 from 100× diffusivity) and contributes nothing to the flip.

## What the evidence does *not* establish

1. **Not identifiability (rule 7).** Local FIM at one operating point; only
   three parameters free; function-valued `j0_neg`/`D_e` perturbed by a
   constant multiplier; other parameters (porosities, conductivities,
   positive-electrode parameters, further kinetics) fixed.
2. **Not experimental validation (rule 8).** Every curve is model-generated.
   No GITT dataset meeting §2.7 has been acquired (T6 still blocked on
   licensing).
3. **Not a pure transport estimator.** The GITT pulse drop and sqrt(t) slope
   contain ohmic and kinetic overpotential.
4. **Threshold sensitivity.** The `OBSERVABLE` flip is a *conservative
   classification flip*: the voltage-only joint set already meets the
   relative-SE limb (0.47 %) and misses only the per-block mean-|S| limb
   (0.0476 vs 0.05). A different, equally defensible threshold would label the
   voltage-only set observable too. The information claim (SE reduction 1.41×,
   joint 1.79× over voltage-only) is more robust than the label.

## Where the action is enforced

`src/pybamm_closed_loop/assembly/observability.py::load_observability` reads
recorded `results/p2/` artifacts and maps them to `OBSERVABLE → CALIBRATE`,
`UNOBSERVABLE → MEASURE/FIX` (accuracy-critical), and
`assembly/report.py::_apply_observability_upgrade` applies that to the dossier
deterministically with a rule-firing transcript. Today it reads only the
voltage-only P2 artifact, so the dossier says `MEASURE`. The v0.3 GITT
artifacts are **not** consumed by that join; nothing in the dossier changed.

## Options for the owner

| option | what it means | consequence |
|---|---|---|
| **A. Keep `MEASURE` (default, no change)** | the diagnostic stands as evidence that a GITT experiment *would* identify `D_neg`; wait for real data before freeing it | nothing to implement; §2.7 guides the T6 dataset search |
| **B. Integrate the low-SOC GITT protocol into the observability join** | `load_observability` also reads the v0.3 artifact (declared protocol: 20 % SOC, 0.2C GITT), and the join upgrades the dossier to `CALIBRATE` | code change in `assembly/observability.py` + tests + a recorded rule-firing entry; dossier output changes; **needs explicit approval** |
| **C. Conditional `CALIBRATE`** | keep `MEASURE` now; upgrade only when a dataset meeting §2.7 exists and a synthetic joint recovery + profile likelihood on that data supports it | recommended; keeps rule 7/8 separation intact |

Recommendation: **C**, with A as the immediate state. The measurement
specification (§2.7) is the deliverable that makes `MEASURE` actionable, and
the synthetic joint-recovery / profile-likelihood study on acquired data is the
next scientific gate before B is even discussable.

## Decision record

- owner decision: **C — conditional `CALIBRATE`** (2026-11-27)
- decided by / date: owner / 2026-11-27
- dossier changed: **no** (rule 10) — the action stays `MEASURE` and
  `assembly/observability.py` is unchanged

### Gate for the upgrade to `CALIBRATE` (all four required)

1. an experimental dataset meeting `docs/EXPERIMENTAL_DATA_REQUIREMENTS.md`
   §2.7 is acquired and licence-verified (T6; currently blocked);
2. synthetic joint parameter-recovery on that dataset's protocol (fit
   `D_neg` + `j0_neg` + `D_e`, multiple starting points) recovers `D_neg`
   within the declared tolerance;
3. a profile likelihood for `D_neg` on the same data is closed (not flat /
   unbounded);
4. the calibration/validation split is defined before fitting (rule 9), and
   the identifiability evidence is kept separate from validation evidence.

Until all four are recorded, any dossier change to `CALIBRATE` is a rule-10
violation.
