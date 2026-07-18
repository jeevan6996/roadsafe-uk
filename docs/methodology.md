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
