# Count-model feasibility POC

Run: 8 September 2026. Purpose: choose the next investigation, not select a
production model. No model is promoted and the map is unchanged.

## Questions and fixed design

Compare exact one- versus two-year feature lags, an exposure-rate baseline,
ridge-Poisson and a nonlinear Poisson histogram-boosting challenger. Evaluate
each unmodified and with a separate multiplicative calibration factor.

- Fit on 2021, calibrate on 2022, explore performance on 2023. The original
  benchmark's 2024 outcomes are not used for fitting, calibration or scoring.
- Both lags use identical segment-year intersections in every period: 240 fit,
  225 calibration and 219 evaluation rows. One-year history originally retained
  719 rows; two-year history retained 684. Pairing excludes the additional 35.
- Five held-out-authority folds; exclude the scoring authority and its stable
  road keys from both fitting and calibration. All six model/lag combinations
  completed every fold. Evaluation group sizes are 1, 35, 29, 143 and 11: pooled
  performance is dominated by one authority, not five equally strong replications.
- Reuse existing training-only categorical encodings and the ridge penalty 0.01.
  Boosting uses 100 iterations, seven maximum leaves, minimum leaf size 20,
  learning rate 0.05, L2 penalty 1.0, seed 42 and no early stopping or parameter
  search. It gets the same encoded road features, not additional outcome history.
- Boosting predicts KSI per million historical vehicle-km, weighted by exposure,
  then converts the rate to a count. This follows the exposure-weighted Poisson
  formulation in [scikit-learn's official example](https://scikit-learn.org/stable/auto_examples/linear_model/plot_poisson_regression_non_normal_loss.html).
- Calibration multiplies predictions by the 2022 observed/predicted total ratio
  from non-held-out authorities. The held-out 2023 outcomes never fit this factor.

The POC contract uses its `test_years` field for 2023 exploration; it is not a
new, untouched confirmatory test set. Only one fitting year is available for this
matched-lag design, and it is pandemic-era data.

## Results on the same 219 evaluation links

| Lag | Model | Calibration | MAE | RMSE | Observed/predicted | Top-10% count recall |
| --- | --- | --- | ---: | ---: | ---: | ---: |
| 1 | Exposure baseline | None | 0.7455 | 1.4234 | 0.5601 | 0.1235 |
| 1 | Exposure baseline | 2022 factor | 0.6313 | 1.1350 | 0.7388 | 0.1235 |
| 1 | Ridge-Poisson | None | 0.6297 | 0.9264 | 0.5728 | 0.2346 |
| 1 | Ridge-Poisson | 2022 factor | 0.5401 | 0.7846 | 0.7422 | 0.2346 |
| 1 | Poisson boosting | None | 0.7165 | 1.2769 | 0.5702 | 0.1235 |
| 1 | Poisson boosting | 2022 factor | 0.6097 | 1.0269 | 0.7490 | 0.1235 |
| 2 | Exposure baseline | None | 0.6036 | 1.0635 | 0.7987 | 0.1235 |
| 2 | Exposure baseline | 2022 factor | 0.6360 | 1.1481 | 0.7246 | 0.1235 |
| 2 | Ridge-Poisson | None | 0.5044 | 0.7024 | 0.8305 | 0.2099 |
| 2 | Ridge-Poisson | 2022 factor | 0.5349 | 0.7387 | 0.7362 | 0.2099 |
| 2 | Poisson boosting | None | 0.5836 | 0.9785 | 0.8145 | 0.1358 |
| 2 | Poisson boosting | 2022 factor | 0.6124 | 1.0403 | 0.7363 | 0.1235 |

Two-year raw ridge has the lowest errors and a ratio closer to one, but one-year
ridge has better count recall. There is no winner on every objective. Calibration
helps one-year models and hurts two-year models: a previous year's correction
can be wrong for a changed distribution. A constant factor preserves ranking
within a fold, but different fold factors can change pooled rankings.

These figures cannot be compared directly with the earlier 2024 benchmark:
the years, training size and retained cohort differ. No confidence intervals
or statistical superiority claims are made.

## Timing discovery: inputs and labels both matter

DfT published its [2023 annual traffic release](https://www.gov.uk/government/statistics/road-traffic-estimates-in-great-britain-2023)
on 22 May 2024. A year-minus-one measurement is therefore not automatically
available by the preceding year-end. This is release-level evidence, not a
complete verification of every archived count-point input and revision.

DfT's [final 2022 casualty statistics](https://www.gov.uk/government/statistics/reported-road-casualties-great-britain-annual-report-2022)
were published on 28 September 2023. Thus this POC's calibration on final 2022
outcomes cannot support an operational forecast made at the end of 2022.
Excluding evaluation labels avoids direct outcome leakage but does not fix
publication-time leakage. Two-year features alone do not solve label timing.

## Paths worth pursuing

1. **Prioritise publication-aware, two-year ridge.** Build an as-of availability
   manifest for every feature and label source. Add more historical fitting
   years and rolling-origin evaluation before deciding the longer lag is robust.
   The present point-error result supports investigation, not promotion.
2. **Keep calibration conditional, not automatic.** Try corrections fitted on
   genuinely available older out-of-time outcomes and compare against no
   correction. Check authority-level errors and drift before pooling results.
3. **Keep boosting as a tested challenger, not the headline.** This configuration
   did not beat ridge. More complexity is not justified by these inputs. A later
   ablation could test publication-safe historical collision rates or road-layout
   features, with identical cohorts and explicit acquisition requirements.
4. **Defer graph/deep models and model-agreement UI.** Broader geography,
   richer defensible features and uncertainty evaluation are more useful next
   than adding another model name to a 219-link experiment.

## Reproduce and inspect

```bash
python -m pip install -e '.[dev,poc]'
OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 python -m roadsafe.poc \
  --panel data/processed/contract-v1/segment-year-panel.parquet \
  --contract configs/poc-count-models-v1.json \
  --output data/processed/poc-count-models-v1

OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 pytest tests/test_poc.py
```

The output contains two lag panels and exclusion reports, per-fold diagnostics,
pooled metrics only when all folds complete, and prediction Parquet. JSON records
input, contract, implementation and prediction fingerprints plus package versions.
Use a fresh output directory for every run; an existing directory is refused
without overwriting its artifacts. The standalone CLI reports
`completed-exploratory` and exits zero only when every experiment completes.
Incomplete experiments report `partial-exploratory` and exit one; successful-fold
predictions can remain in that new run for diagnosis, but are not complete-run
results. No-prediction runs record a null prediction fingerprint.
Dependencies used locally: NumPy 2.5.1, Polars 1.42.1, statsmodels 0.14.6 and
scikit-learn 1.9.0. Generated data remain outside Git.

Regression tests cover invalid calibration inputs, geographic and changing-road
identity exclusion, scoring-outcome independence, exposure scaling, deterministic
repeats and independence from changed 2024 outcomes. CI installs the optional POC
extra to exercise the boosting tests; without that extra those tests are skipped.

## Release reproduction, 27 October 2026

Reran the documented real panel and contract through the corrected standalone
command into `data/processed/poc-release-check-2026-10-27`, with the existing
Python 3.14 environment and one OpenMP/BLAS thread. All six model/lag combinations
completed. Metrics match the table above to its displayed precision. The new
report SHA-256 is
`7979ba33c51598f3a00dceffedf531f8aba7ed8364a9a3aec8d9dad3bbd9e305`.
The result remains exploratory and unpromoted; rerunning the same development
cohort is reproducibility evidence, not fresh confirmatory evaluation.
