# Methodology and experiment gates

## Primary analytical target

The planned target is the future killed-or-seriously-injured count for a road
segment over a fixed period. Event-level severity classification is a separate
research question and will not be presented as preventive risk screening.

## Baseline ladder

1. Historical count and multi-year average.
2. Traffic-exposure-adjusted rate.
3. Negative-binomial Safety Performance Function.
4. Empirical Bayes expected frequency.
5. Hierarchical Bayesian count model.
6. Calibrated boosted-tree challenger.
7. Emerging-pattern detector.
8. Road-network graph model.

## Promotion rule

A candidate must be evaluated on future years and unseen authorities. It must
publish calibration, ranking lift, subgroup performance, uncertainty, and a
comparison against simpler methods. A complex model that does not add reliable
value will remain an archived experiment.

## Leakage rule

Only information available before the prediction period may be used. Weather,
lighting, and road-surface conditions observed during a future collision are
not valid occurrence-model features.

## Network matching gate

Collision matches are accepted only within 50 metres of a DfT major-road link.
A match is marked ambiguous when the second candidate is within 10 metres of
the nearest candidate. Ambiguous and out-of-range records are excluded from
segment aggregation and reported separately.

## Exposure interpretation

The descriptive rate is collisions per 100 million annual vehicle-kilometres,
using AADF and DfT link length. It is not an expected collision frequency and
is not adjusted for regression to the mean, road characteristics, uncertainty,
or exposure-estimation quality.

The versioned evaluation contract is stored in
`configs/evaluation-v1.json`. Its status remains `planned-not-run` until the
multi-year pipeline exists and all declared temporal and geographic tests have
actually executed.

## Panel readiness gate

`roadsafe build-panel` assembles annual evidence using the stable DfT count
point key while retaining each year's geometry-specific segment identifier.
Before any baseline or model is fit, it reports:

- missing training, validation, or test years
- duplicate segment-year records
- missing, non-finite, or non-positive exposure
- missing, non-finite, negative, fractional, or out-of-range KSI targets
- nonnumeric exposure/count types, including text and booleans
- absent or incomplete fields for every required subgroup
- fewer than two local-authority groups for geographic holdout
- no validation or test authority unseen during training
- the number of segments with complete contract-period history

The readiness report records the training, validation, test, and unseen
authority sets explicitly. A panel with repeated authorities across every
period is blocked even when it contains multiple authorities, because it does
not support a genuinely geographic holdout. Local authority, road
category, road type, and traffic estimation method flow from the official AADF
source. Urban/rural status is joined from the documented ONS/Defra small-area
source rather than inferred from road category or authority.

The exposure-rate baseline and Empirical Bayes producer apply these numeric
checks independently to their training and scoring rows, so calling either
producer directly cannot bypass readiness validation. KSI counts must be
nonnegative integers representable by an unsigned 64-bit artifact column.
Integer-valued floats and exact integral Decimals are accepted; scoring exports
normalise them to `UInt64` for the serving API's strict integer contract. Decimal
integrality is checked before any floating-point conversion used for finiteness.
Zero counts remain valid. Rows outside the contract's years are not scored.

Invalid scoring inputs, non-finite derived values and numerical overflow fail
before successful output artifacts are written. Reports use strict JSON rather
than emitting NaN or Infinity as if they were valid estimates. These guards do
not establish calibration, uncertainty validity or model promotion. An I/O
failure during writing can still leave partial outputs; atomic multi-file
publication is not claimed by this correction.

The Empirical Bayes screening layer fits a Gamma prior over segment collision
rates using training years only. Its Poisson-gamma posterior combines the
training prior with each observed scoring-period count and exposure, producing
an exposure-scaled expected frequency and a non-negative excess-frequency
signal. The report includes the prior rate, prior shape, uncertainty proxy, and
split-level observed-versus-expected totals. This is intentionally a
retrospective screening estimate: because it uses the observed scoring-period
count, it must not be described as a future prediction or causal intervention
effect. It is retained as an analytical layer until comparison with the SPF
and calibrated challengers is complete.

The experimental NB2 Safety Performance Function uses the same panel contract,
fits only on declared training years, and uses the log of annual vehicle-km as
an exposure offset. Categorical road and exposure-quality fields are encoded
from training data only; unseen scoring levels use the reference category.
Predictions are written with validation/test split labels and compared with the
exposure-rate baseline. The model is not promoted until future-period,
unseen-authority, calibration, subgroup, and ranking evidence supports it.
The current West Yorkshire panel has repeated authorities across all years, so
the report blocks readiness for the future geographic holdout and also includes
deterministic leave-one-authority-out folds for every training authority as a
separate internal benchmark. The aggregate is not a substitute for a future
holdout because each fold still uses historical observations from the held-out
authority.

The SPF report additionally includes `future_authority_holdout`. Each fold fits
on training years in other authorities and scores only the excluded authority's
validation/test years. Stable segment identities in that scoring fold are also
excluded from fitting, even if their authority code changed. Feature encodings
and the comparison baseline are fitted again inside each fold. Per-fold and
aggregate validation/test metrics, authority/year membership, failed fits and
row coverage are recorded. Aggregates cover successful folds only and must not
be compared with metrics from a different set of rows.

This is an internal spatiotemporal backtest, not untouched external validation.
It does not resolve feature timing: the current SPF uses scoring-year AADF and
attributes, rather than a verified prior-year feature snapshot. Reports therefore
explicitly block promotion with `prior_year_feature_availability_not_verified`.
Neither a successful fit nor a lower MAE alone makes this a deployable forecast.

The separate [lagged experiment](lagged-benchmark.md) now replaces all declared
SPF covariates with exact historical snapshots and compares a ridge-Poisson
model with the same historical-exposure baseline. This establishes calendar
lagging, not verified publication-time availability. It leaves the original
same-year benchmark unchanged and retains the promotion block.

Ranking precision is the fraction of selected segment-year rows with at least
one KSI collision. `mean_ksi_at_10_percent` separately records collisions per
selected row, which can exceed one. Recall and lift remain collision-count
weighted: recall is the fraction of all observed KSI collisions captured by
the selected rows. Tied predictions retain input order.

The network build supports an explicit urban/rural lookup keyed by
`count_point_id` and `year`. Missing lookup data is represented as null rather
than inferred, so subgroup readiness remains auditable.

`roadsafe build-contract` executes the artifact build for every year declared
by the contract before invoking the same readiness gate. It is an orchestration
step only: a blocked report remains the correct outcome until every declared
source year and subgroup field is present.
