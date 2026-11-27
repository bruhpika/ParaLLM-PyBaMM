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
| observable-augmented study (2026-11-27, twice corrected) | `results/observables/diffusivity_multi_observable_fim.{json,md}` | low-SOC GITT pulse drop 0.082, sqrt(t) slope 0.100 clear the 0.05 \|S\| bar; verdict flips to `OBSERVABLE` under the declared conjunction. **True** SE reduction from adding GITT + EIS: **1.007×** (3.42 % → 3.39 %) — the flip is a classification flip driven by the \|S\| limb, not by added precision |
| protocol correction | same artifact + `CHANGELOG.md` | the first run used the PyBaMM default 100 % SOC where the graphite OCP is flat; its null was a protocol artefact. Committed protocol: 20 % SOC, 0.2C, 120 s pulse / 180 s rest × 5 |
| unit correction | same artifact + `CHANGELOG.md` | the first two runs mixed dimensionless sensitivities with noise in volts, scaling every implied SE by its observable's `y_scale`; corrected to raw sensitivities with noise in observable units. Feature noises are propagated from the 1 mV per-sample noise |
| joint collinearity check (2026-11-27, corrected) | `results/observables/joint_diffusivity_fim.{json,md}` | `D_neg`, `j0_neg`, `D_e` free together: `D_neg` marginal rel. SE **4.52 %** (single-parameter 3.39 %, variance inflation **1.78**), correlations 0.36 / −0.655 / −0.657, all below the declared 0.9 warning; classification `OBSERVABLE` by 0.5 percentage points; stable across 0.5–5 % FD steps |
| recovery + profile dry-run (2026-11-27, synthetic) | `results/observables/diffusivity_gitt_recovery.{json,md}` | joint least squares on §2.7 GITT raw voltage: `j0_neg` recovered (z = 0.23), `D_neg`/`D_e` within their SEs (z = −0.52 / 0.86) but failing the multi-start spread rule (1.15 / 1.12 > 1.05) because of a shallow `D_neg`–`D_e` valley (ρ = −0.899 GITT-only). Profile over `D_neg` **closed** at [0.35, 0.82] (95 %): bounded, not pinned |
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
4. **Threshold sensitivity and limited precision.** After the unit correction
   both the voltage-only and the augmented sets clear the 5 % SE limb
   (3.42 % / 3.39 %), so the flip is decided entirely by the per-block mean-|S|
   limb (0.0476 vs 0.100). In the joint fit `D_neg` reaches 4.52 % — 0.5
   percentage points of margin against the same 5 % rule. The label is
   threshold-sensitive; the honest quantitative statement is that `D_neg` is
   *locally bounded to ≈ ±4.5 % (1σ)* under the declared noise, that GITT
   contributes ≈ 0.7 % additional information over three discharge curves, and
   that a §2.7 GITT dataset alone bounds it at ±45 % (95 %) rather than pinning
   it.

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

### Gate machinery dry-run (2026-11-27) — synthetic only, gates NOT satisfied

The procedures for gates 2 and 3 are implemented and validated on
model-generated data:

- `benchmarks/observables/diffusivity_gitt_recovery.py` with
  `configs/v03/diffusivity_recovery.yaml`, artifact
  `results/observables/diffusivity_gitt_recovery.{json,md}`;
- joint weighted least-squares recovery of the three scale factors from the
  §2.7 GITT voltage series, from four declared starting points, judged by a
  declared rule (`|z| ≤ 3` against the truth-FIM standard error **and**
  multi-start estimate spread ratio ≤ 1.05);
- a profile likelihood over `D_neg` (other two re-optimised at each of 11
  declared grid points), judged closed when the cost exceeds the minimum by
  the 95 % χ² critical value (3.841, one parameter) on **both** sides;
- parameters touching a null direction of the truth FIM are reported as
  unconstrained with infinite standard error and are never counted as
  recovered (the tiny SPM integration test pins this honesty property).

This proves the machinery executes and behaves correctly. **It does not
satisfy gates 2/3**: the data are model-generated at a declared truth point
(rules 7/8), and both gates must be re-run on the real dataset from gate 1
before the action is reconsidered.

Dry-run outcome (artifact `diffusivity_gitt_recovery.json`): `j0_neg` recovers
(z = 0.23); `D_neg` and `D_e` land inside their predicted SEs (z = −0.52 /
0.86) but fail the multi-start spread rule (1.15 / 1.12 > 1.05) because of a
shallow `D_neg`–`D_e` valley (ρ = −0.899 on GITT-only). The profile likelihood
over `D_neg` is **closed** at [0.35, 0.82] (95 %, χ² = 3.841): the parameter is
bounded but only to ≈ ±45 %. Both findings argue for strengthening the
measurement specification (more titrations, longer rests, and at least one
non-GITT observable to break the `D_neg`–`D_e` valley) before real data are
collected.
