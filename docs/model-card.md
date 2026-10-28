# Model and evidence card

Status: experimental pilot, reviewed 8 September 2026. No forecasting model is
promoted. This card distinguishes working software from validated predictive
performance. The intended task is prioritising road links for investigation,
not predicting individual crashes or choosing interventions.

Follow-on: the [count-model POC](poc-count-models.md) compares two lag choices,
calibration and Poisson boosting on a separate 2023 cohort. It does not replace
the 2024 results below or change promotion status. It also identifies calibration
label publication timing as an additional operational blocker.

## Data and target

- Source: official DfT STATS19, Major Roads Database and AADF evidence.
- Unit: major-road segment-year; target: KSI collision count, not casualty count.
- Observed 2024 pilot: 1,791 collisions and 256 links. Matching accepts 330
  collisions within 50 metres, excludes 61 ambiguous and 1,400 out-of-scope cases.
- Lagged experiment: 1,269 candidate rows, 1,217 retained, 52 without history
  excluded. Training 2020-2022: 716 rows; validation 2023: 247; test 2024: 254.
- Exact prior-calendar-year exposure and categorical road features are used.
  A lag does not prove that the data were published before the forecast cutoff.

## Approaches tried

| Approach | What was achieved | What must not be inferred |
| --- | --- | --- |
| Training-only global exposure rate | Transparent benchmark, refitted within each fold | A descriptive current-year rate is not a future forecast |
| Poisson-gamma Empirical Bayes | Training-period prior plus observed-period counts produces retrospective shrinkage and excess-frequency evidence | This uses the scoring-period outcome; it is not a forecasting competitor |
| Unpenalized negative-binomial NB2 SPF | Count regression with exposure offset and explicit fit diagnostics | The lagged fit failed; do not present it as successful |
| Ridge-Poisson SPF | Separate regularized model, fixed penalty 0.01 on non-intercept coefficients; all five joint folds completed | Convergence and lower errors do not establish deployment readiness |

The lagged NB2 training set contains 14 TA-category rows with zero KSI events.
The fit drove that coefficient to approximately -43 and became nonfinite, despite
a full-rank design. The ridge model is an explicitly separate experiment, not a
silent NB2 fallback. Its acceptance check requires finite coefficients and a
maximum absolute penalized gradient of 1e-5. See the
[benchmark report](lagged-benchmark.md) for the diagnosis and reproduction commands.

## Paired held-out results

Future-year/leave-one-authority-out test evaluation, 254 retained 2024 rows.
Each scoring authority and its stable segment identities are excluded from
fitting; encodings and the baseline are fitted on that fold's training data.

| Metric | Ridge-Poisson | Exposure baseline |
| --- | ---: | ---: |
| MAE | 0.512612 | 0.567162 |
| RMSE | 0.788730 | 1.106468 |
| Observed / predicted total count | 0.668433 | 0.702816 |
| KSI collision-count recall in top 10% of links | 0.253333 | 0.120000 |

Lower errors and better count-weighted ranking are encouraging, but calibration
is worse on this ratio: both models overpredict, and the ridge ratio is further
from one. These are point estimates, not statistically established superiority.
Five pilot-authority folds do not establish national generalisation. The 501
combined validation/test rows exclude 16 future rows with missing history.

The locally generated source report is
`data/processed/contract-v1/lagged-v1/poisson/ridge-poisson-spf-report.json`.
Its SHA-256 at review was
`b65067167e14094ef322ee74c00dd6ab7b64ab8bf85c5281b7bbb5b93e9cf7fd`.
Generated datasets and full reports remain outside Git; reproduction requires
the documented source acquisition and panel workflow. Contract JSON describes
the experimental specification; the generated report, not its static status
label, records whether a run completed.

## Distinctive engineering, not a new algorithm

1. Evidence can be challenged: matching rejections, estimated exposure and
   missing history remain visible instead of being silently filled.
2. Retrospective screening and forecasting are separate data paths. Current
   outcomes cannot enter the lagged SPF design.
3. Joint time/geography backtests prevent memorised road identities from
   masquerading as future generalisation.
4. A selected road exports canonical geometry, evidence, limitations and artifact
   fingerprints, connecting the interface to reproducible analytical inputs.

The proposed next differentiator is an agreement/disagreement investigation view
with coverage and uncertainty, but it requires accepted challengers first.

## Promotion gates

1. Verify historical publication dates and revisions against feature cutoffs.
2. Predeclare calibration and uncertainty thresholds before further selection;
   use validation data for calibration. The inspected 2024 test set is no longer
   untouched for future model-selection claims: reserve new external geography
   or a later reporting period for confirmatory evaluation.
3. Quantify paired uncertainty with grouping-aware resampling. Existing process
   variance proxies omit coefficient uncertainty and are not calibrated intervals.
4. Expand geography and report subgroup/coverage failures, not only pooled scores.
5. Complete browser, accessibility and visual checks before presenting the app
   as demo-ready. No national coverage, real-time inference or intervention
   effectiveness claim is currently supported.
