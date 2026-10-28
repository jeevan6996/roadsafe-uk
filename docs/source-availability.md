# Forecast source availability

## Why this is part of the modelling core

A temporal split is insufficient if a backtest uses data published after the
forecast was supposedly issued. Measurement year, release date and the version
of the actual file are different facts. RoadSafe now has a reproducible source
preflight that checks these separately for features and fitting labels.

The standalone audit is also connected to the fixed-design POC through
`run-poc-bundle`. That entry point audits both lag designs before fitting and
blocks by default. Other model commands remain exploratory and are not gated
by this wrapper. Neither command promotes a model or changes the served app.

## Run a source-audited experiment bundle

```bash
roadsafe run-poc-bundle \
  --panel data/processed/contract-v1/segment-year-panel.parquet \
  --contract configs/poc-count-models-v1.json \
  --manifest configs/source-availability-v1.json \
  --output data/processed/poc-bundle-v1
```

The output directory must not already exist. The command writes a versioned
`run-report.json`, both lag-specific availability reports, and SHA-256 hashes
of the inputs and generated artifacts. With the checked-in source manifest it
exits 1 with `status: blocked`, without fitting models or writing predictions.

For deliberately retrospective research, install `.[poc]` and add
`--allow-exploratory` with a **new** output directory. Blocked source checks are
still recorded; a complete model run is labelled `completed-exploratory`, never
forecast-ready. A partial model run exits 1. Invalid inputs or fitting failures
exit 2; failures after the bundle is created leave a `failed` run report.
Changes to the panel, contract or manifest during execution invalidate the run.

Passing the source audit still does not establish derived-panel lineage or
model promotion. Both remain explicitly false in the bundle. This command
does not recover historical source vintages, independently validate evidence
URLs, or make the existing POC's late calibration labels historically available.

## Run the audit

```bash
roadsafe audit-availability \
  --contract configs/poc-count-models-v1.json \
  --manifest configs/source-availability-v1.json \
  --lag-years 2 \
  --output data/processed/availability-lag2
```

The checked-in manifest is deliberately incomplete: it contains official
release-level evidence, not invented historical file hashes. This command
currently exits **1** and writes both `availability-report.json` and a readable
`availability-report.md`. Invalid configuration exits 2. Satisfied source
requirements exit 0, without asserting model readiness.

Repeat with `--lag-years 1` and a separate output directory to compare timing.
Both reports are deterministic for unchanged input manifests and artifact bytes.
Input and implementation SHA-256 fingerprints are recorded.

## Rules and data lineage

- Training, calibration and scoring feature snapshots each use the end of the
  calendar year preceding that sample year, not the final evaluation cutoff.
- Training and calibration outcome labels must exist by the forecast cutoff
  for each test year. Scoring labels are evaluation-only, not fitting inputs.
- Traffic supplies exposure, road category, road type and estimation method.
  Network geometry defines the historical segment population. Urban/rural
  count-point classifications must cover the corresponding feature year;
  "2011 classification" does not mean the annual count-point file existed in 2011.
- Each source kind/year has one explicitly chosen vintage. A release date alone
  cannot satisfy the audit. Supply a local artifact path, SHA-256, vintage
  availability date and evidence URL together. Paths are relative to the manifest.
- Local bytes must match the declared hash. Missing, revised or post-cutoff
  artifacts block the relevant requirements; no silent fallback to current files.

Evidence URLs are citations for human review, not automatically verified claims.
The audit does not prove that an existing derived panel was built from those
files. Network matching and geographic split metadata have additional lineage
requirements. These remain explicit limits even when every source check passes.

## Current experiment: checked 14 September 2026

The POC fits 2021, calibrates on 2022 and explores 2023. For both one- and
two-year lags, **11 of 11 source-use requirements are blocked** by missing
source evidence, unverified file vintages or release dates after the cutoff.
This is not 11 missing datasets: one artifact can have multiple uses, and local
data availability does not establish historical availability.

| Evidence | Published | Implication |
| --- | --- | --- |
| [2021 traffic](https://www.gov.uk/government/statistics/road-traffic-estimates-in-great-britain-2021) | 28 September 2022 | Release predates the 2023 forecast cutoff, but not the 2022 sample cutoff |
| [2022 traffic](https://www.gov.uk/government/statistics/road-traffic-estimates-in-great-britain-2022) | 13 July 2023 | One-year scoring features were unavailable at end-2022 |
| [2021 final casualties](https://www.gov.uk/government/statistics/reported-road-casualties-great-britain-annual-report-2021) | 29 September 2022 | Release predates the end-2022 fitting cutoff; exact file vintage remains unverified |
| [2022 final casualties](https://www.gov.uk/government/statistics/reported-road-casualties-great-britain-annual-report-2022) | 28 September 2023 | POC calibration cannot support an end-2022 forecast |

The manifest also records the [2023 traffic release](https://www.gov.uk/government/statistics/road-traffic-estimates-in-great-britain-2023)
on 22 May 2024 for auditing later experiments. These are annual statistical
release dates, not proof of the publication date of every individual input file.

## Next implementation and presentation

1. Recover dated source vintages and rebuild a panel whose lineage refers to
   the exact hashes in the manifest. Do not label current revised downloads as
   historical snapshots.
2. Expand earlier fitting years so calibration can use genuinely available
   out-of-time labels, or compare an explicitly uncalibrated model. Keep an
   untouched external geography/time cohort for confirmation.
3. Bind derived-panel lineage to the source-audited experiment bundle, then
   evaluate calibration, ranking and paired uncertainty before promotion.
4. In the repository demo, show the retrospective investigation workflow
   separately from the experimental model card and this availability report.

The distinction to demonstrate is auditable evidence and honest model limits,
not an unsupported claim of algorithmic novelty. A failed analytical gate is
useful evidence when its cause, remedy and reproduction are visible.
