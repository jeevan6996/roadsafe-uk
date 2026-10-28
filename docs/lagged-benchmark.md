# Lagged-feature count benchmark

## Purpose and acceptance criteria

Move the statistical core from same-year explanatory inputs toward an auditable
forecasting experiment. Preserve future labels, prevent prediction-year
covariates from entering the design, disclose missing history, and compare a
stable regularized count model with the exposure-rate baseline on identical
rows and geographic folds. No new serving layer is introduced.

## Feature contract

`build-lagged-panel` joins `(segment_key, target_year - lag_years)` exactly.
It does not use the preceding row, interpolate or fill missing years. Only
exposure, road category/type, urban/rural classification and traffic-estimation
method enter the feature snapshot. Current KSI count remains the target;
current authority is retained for splitting, not fitted as a predictor.
`feature_year` records the source year, and `observed_annual_vehicle_km` is
retained for auditing but is never an SPF input.

The output is a model-specific panel, not replacement observed evidence for
the descriptive map or Empirical Bayes workflow. Missing snapshots and invalid
features/targets are written to a separate exclusion artifact. A contract year
with no usable rows blocks the feature report and is rejected by the model
builder. Input, contract and output checksums preserve reproducibility.

`configs/evaluation-lagged-v1.json` uses 2020-2022 for training because the
available source panel starts in 2019. Validation remains 2023 and test remains
2024. This is a distinct experiment, not a silent change to the original
2019-2022 training contract. All metrics below use the new cohort; comparisons
against the previous report are not paired comparisons.

## Why a separate regularized model

The lagged training panel has 14 TA-category rows with zero observed KSI events.
The unpenalized NB2 fit did not converge; its TA coefficient was approximately
-43 and the optimizer objective became nonfinite. The design matrix itself
was full rank (six columns, condition number approximately 12.2). This is
consistent with a zero-event categorical level driving its unpenalized
coefficient toward negative infinity. The failed NB2 experiment is not relabelled
as successful and there is no silent fallback.

The separate Poisson benchmark uses the existing
[statsmodels GLM regularization implementation](https://www.statsmodels.org/stable/generated/statsmodels.genmod.generalized_linear_model.GLM.fit_regularized.html).
It minimizes negative log likelihood per training row plus an L2 penalty on
non-intercept coefficients. The intercept is unpenalized; the fixed penalty
is 0.01. No validation/test search selected that value. Initialization uses
the training-only global exposure rate. Finite coefficients and a maximum
absolute penalized gradient of 1e-5 are required before accepting a fit.

Feature encodings and the baseline rate are refitted inside each geographic
fold. The scoring authority and its stable segment identities are excluded
from training. Separate filenames prevent overwriting the NB2 experiment.

## Real-panel results, 7 September 2026

- Candidate rows: 1,269; retained: 1,217; excluded for missing history: 52.
- Training rows: 716; validation rows: 247; test rows: 254.
- All five joint future/authority folds completed, covering all 501 retained
  scoring rows. This is not full-source coverage: 16 future rows lacked history.

| Evaluation | Metric | Ridge Poisson | Exposure baseline |
| --- | --- | ---: | ---: |
| Temporal test, known authorities | MAE | 0.460 | 0.522 |
| Temporal test, known authorities | RMSE | 0.723 | 1.015 |
| Future/held-out-authority test | MAE | 0.513 | 0.567 |
| Future/held-out-authority test | RMSE | 0.789 | 1.106 |
| Future/held-out-authority test | Observed/predicted ratio | 0.668 | 0.703 |
| Future/held-out-authority test | Collision-count recall, top 10% | 0.253 | 0.120 |

The model improves point errors and count-weighted ranking on this pilot, but
still overpredicts total held-out counts. That is not a deployment-quality
calibration result or evidence of a causal intervention effect.

## Remaining gates

1. Verify source publication dates and historical revisions. A prior-year
   measurement is not necessarily published before the prediction cutoff.
2. Declare calibration and uncertainty acceptance thresholds before additional
   challenger selection. Current normal process-variance bounds exclude
   coefficient uncertainty and are not calibrated predictive intervals.
3. Quantify paired uncertainty using segment/authority-aware resampling and
   expand external geography; five pilot authorities do not establish national
   generalization.
4. Only after those checks, evaluate boosted-tree challengers and surface
   model agreement in the product. Keep current outcomes out of forecasting
   inputs and retrospective Empirical Bayes separate from prediction.

The report therefore keeps `model_promoted: false`. Tests, fit convergence,
and improved MAE are necessary evidence, not sufficient promotion criteria.

## Implementation checks

The increment passes `make check` (Ruff, strict mypy and TypeScript), `make test`
(102 Python tests and one frontend test), the frontend production build and
`git diff --check`. Both documented CLI commands were exercised on the local
official-data panel. Tests include zero-event categories, the intercept-only
exposure-rate solution, future-target independence, missing history, invalid
numeric values, missing contract years and exact feature chronology. These
checks are distinct from the remaining statistical promotion gates.
