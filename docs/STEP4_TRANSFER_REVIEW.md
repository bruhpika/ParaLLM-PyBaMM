# Step 4 — current/capacity transfer review

## Decision counts

From the repository root, where `--p2-results results/p2` is present:

```
.venv/bin/parallm --quiet --json assemble --target configs/v2/target_lgm50.yaml --registry data/registry/registry.json --out /tmp/step5/LGd
LG M50  {"CALIBRATE": 6, "FIX": 18, "REVIEW": 52, "USE": 20}

.venv/bin/parallm --quiet --json assemble --target configs/v3/target_lfp_graphite_prada2013.yaml --registry data/registry/registry.json --out /tmp/step5/LFPd
LFP     {"FIX": 14, "REJECT": 9, "REVIEW": 66, "USE": 7}
```

| Target | Corrected rubric-v5 counts |
|---|---|
| NMC / LG M50 (`configs/v2/target_lgm50.yaml`) | CALIBRATE 6, FIX 18, REVIEW 52, USE 20 |
| LFP / Prada2013 (`configs/v3/target_lfp_graphite_prada2013.yaml`) | FIX 14, REJECT 9, REVIEW 66, USE 7 |

The earlier table said LG M50 FIX 19 / USE 25 with no CALIBRATE. That was
wrong: it omitted the observability join from `results/p2`, which reclassifies
six parameters as `CALIBRATE`. The counts above are from the command output.

The only change is `current_function`: `USE` → `REVIEW` on the LFP target.
It is unchanged (`USE`) on the LG M50 target because that target's stated cell
build matches the candidate's stated LG M50 conditions.

**Why the version was bumped to `rubric-v5`:** the `is_cell_specific`
classification is a rubric input, and adding `current_function` changes a
decision. The weights and scoring rules are unchanged; the bump makes the
decision set auditable. The lexicon change also affects rubric-v4 if that
version is requested explicitly, because `stated_transfer_matches()` reads the
same classification at every version.

## `current_function`

The LG M50 value is `5.0` A with stated conditions
`cell = LG M50 21700 cylindrical cell`, no chemistry family, temperature not
stated. On the LFP target it is now `REVIEW` (cell-specific value without a
stated target-cell match); on LG M50 it remains `USE`.

## Other capacity- or current-dependent parameters (LFP v5 decisions)

| Parameter | Decision |
|---|---|
| current_function | REVIEW |
| nominal_cell_capacity | REVIEW |
| number_of_cells_connected_in_series_to_make_a_battery | FIX |
| number_of_electrodes_connected_in_parallel_to_make_a_cell | FIX |
| neg_exchange_current_density | USE |
| neg_reaction_rate | USE |
| pos_exchange_current_density | REJECT |
| pos_reaction_rate | REJECT |
| neg/pos_activation_energy | USE / REJECT |
| neg/pos_current_collector_thickness | REVIEW / REVIEW |
| *_current_collector_{conductivity,density,specific_heat_capacity,thermal_conductivity} | REVIEW |
| *_electrode_{double_layer_capacity,specific_heat_capacity} | REVIEW / REVIEW |
| sei_kinetic_rate_constant, sei_reaction_exchange_current_density | REVIEW |
| separator_specific_heat_capacity | REVIEW |
| contact_resistance | FIX |

These were reviewed, not silently reclassified. Only `current_function` was
changed in this step.

## LFP `USE`/`FIX` values sourced from graphite-SiOx (owner decision pending)

Graphite vs graphite-SiOx matching was **not** changed. These are the LFP
`USE`/`FIX` values whose stated conditions mention graphite-SiOx / bi-component
graphite, with those conditions verbatim:

| Parameter | Decision | Value | Stated conditions |
|---|---|---|---|
| contact_resistance | FIX | 0 Ohm | cell: LG M50 21700 cylindrical cell (70.00 mm x 21.00 mm, 68.38 g with can); chemistry: NMC 811 / bi-component graphite-SiOx negative (10 wt% SiOx); T 298.15 K |
| neg_activation_energy | USE | 35000 J mol-1 | cell: graphite-SiOx half cell (Li counter); T 303.15–333.15 K |
| neg_bruggeman_electrode | FIX | 0 dimensionless | cell: LG M50 21700 cylindrical cell; chemistry: NMC 811 / bi-component graphite-SiOx (10 wt% SiOx); T 298.15 K |
| neg_electrode_ocp | USE | graphite_LGM50_ocp_Chen2020 | cell: graphite-SiOx half cell and three-electrode full cell; T 298.15 K |
| neg_entropic_change | FIX | 0 V.K-1 | cell: LG M50 21700 cylindrical cell; chemistry: NMC 811 / bi-component graphite-SiOx (10 wt% SiOx); T 298.15 K |
| neg_exchange_current_density | USE | graphite_LGM50_electrolyte_exchange_current_density_Chen2020 | cell: graphite-SiOx half cell (Li counter), from LG M50; T 298.15 K |
| neg_particle_diffusivity | FIX | 3.3e-14 m2.s-1 | cell: graphite-SiOx half cell (Li counter), from LG M50; T 298.15 K |
| neg_reaction_rate | USE | 6.48e-7 A m-2 (m3 mol-1)1.5 | cell: graphite-SiOx half cell (Li counter); T 298.15 K |
| negative_electrode_reaction_driven_lam_factor | FIX | 0 m3.mol-1 | cell: LG M50 21700 cylindrical cell; chemistry: NMC 811 / bi-component graphite-SiOx (10 wt% SiOx); T 298.15 K |
| number_of_cells_connected_in_series_to_make_a_battery | FIX | 1 dimensionless | cell: LG M50 21700 cylindrical cell; chemistry: NMC 811 / bi-component graphite-SiOx (10 wt% SiOx); T 298.15 K |
| number_of_electrodes_connected_in_parallel_to_make_a_cell | FIX | 1 dimensionless | cell: LG M50 21700 cylindrical cell; chemistry: NMC 811 / bi-component graphite-SiOx (10 wt% SiOx); T 298.15 K |

The owner must decide which of these should remain `USE`/`FIX` for a
graphite-only LFP target and which should become `REVIEW`. No change is made
here.
EOF
echo done