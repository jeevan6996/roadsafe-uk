# September 2026 progress review

## Source-audited experiment bundles, 30 September

Connected the availability preflight to `roadsafe run-poc-bundle`. Both lag
designs are audited before the fixed count-model POC can fit. Missing evidence
blocks by default; `--allow-exploratory` permits explicit research runs without
removing source blockers or claiming panel lineage or model promotion.

The versioned run report records input hashes, each source-audit summary,
generated artifact hashes, and completed/partial/failed state. Existing output
directories are rejected so stale predictions cannot masquerade as new results.
Changes to panel/contract/manifest bytes during a run invalidate the bundle.
The original exploratory POC and other model commands remain separate; this
is not a global production forecasting gate.

Real-pilot preflight output: `data/processed/poc-bundle-2026-09-30`. Both lags
remain blocked on 11 of 11 requirements. The command exited 1 and created no
model predictions, as intended. No new real-data model performance is claimed.

Validation: 147 Python tests (including nine new bundle tests) and 12 frontend
tests passed. Bundle tests exercise both real synthetic model runs and blocked,
partial, exception, input-mutation and reused-output cases. Ruff lint/format,
strict mypy, frontend/E2E TypeScript and whitespace checks passed. The existing
physical-core-detection warning remains nonfatal. No browser rerun or remote CI
is claimed for this backend/CLI increment. Changes remain local and unpushed.

Next analytical requirement is still dated source vintages and derived-panel
lineage, then an available-label experiment design with predeclared calibration
and uncertainty criteria. This orchestration increment does not satisfy those
evidence requirements. The existing RoadSafe demo remains retrospective.
Next sequential project increment remains ReWear's licensed real-image retrieval
benchmark; no ReWear or SpectraHeat files changed during this pass.

## Browser-verified pilot demonstration, 14 September

Added three opt-in Playwright acceptance tests against the real full-pilot API:
desktop investigation/export and 390/320-pixel mobile workflows. The desktop
download is checked against canonical API geometry, observed counts and source
fingerprints. The tests check empty search, selection persistence, clearing,
mobile page overflow and successful desktop basemap responses. Screenshots
are now linked from the README and [demo guide](demo.md).

Initial visual inspection exposed captures taken during map movement/loading.
The map now exposes its busy state from loading, movement and idle events, with
a unit regression test; screenshots wait for idle. MapLibre was updated to
6.9.1 and Vitest to 4.1.11 following dependency advisories. Browser tests and
their configuration are included in TypeScript checking.

Validation: 138 Python tests, 12 frontend tests and three real Chromium tests
passed. Ruff lint/format, strict mypy, frontend/E2E TypeScript, production build
and whitespace checks passed. The dependency installation reported zero known
vulnerabilities. Python emitted a physical-core-detection warning with logical
core fallback; it did not fail tests. No remote CI or new model run is claimed.
Changes, including screenshots, remain local and unpushed.

The UI is a local retrospective investigation demo, not a validated forecast.
Generalized DfT link geometry visibly differs from precise basemap road traces;
validate geometry and matching sensitivity before stronger location-specific
claims. A complete keyboard/accessibility audit, other browser engines, video
recording and public deployment remain pending. The source-vintage and forecast
calibration gates below are unchanged.

Next sequential project increment: ReWear's licensed real-image retrieval
benchmark with identity-safe splits, baseline comparison and failure examples.
RoadSafe's next analytical increment remains archived source vintages and
derived-panel lineage; do not promote a model based on presentation progress.

## Source-availability preflight, 14 September

Implemented `audit-availability` with strict source manifests, explicit annual
feature cutoffs, forecast-time training/calibration label checks, local artifact
hash verification and deterministic JSON/Markdown reports. Missing records,
unverified vintages and late publications remain separate blockers. The CLI
returns a nonzero status for an unsatisfied audit without hiding the report.

Ran one- and two-year POC designs against the researched official-release
manifest: both have 11 blocked source-use requirements. This does not negate
the exploratory results; it prevents presenting them as operational forecasts.
The 2022 calibration labels are too late for the end-2022 prediction cutoff,
and annual release pages alone cannot prove historical count-point file versions.

Validation: 138 Python tests passed, including 17 new audit tests; 11 frontend
tests, production build, Ruff, formatting, strict mypy and frontend TypeScript
passed. No new trained model,
public demo, visual QA or remote CI result is claimed. Browser tooling was not
available in this session. Changes remain local and unpushed.

Next: recover dated source vintages, bind rebuilt panel lineage to the manifest,
then connect the preflight to model runs. Retrospective demo visual acceptance
remains a separate open task. ReWear and SpectraHeat were not modified in this
increment; their existing handoffs below remain the sequential plan.

See [the audit design and evidence](source-availability.md).

## Count-model POC, 8 September

Implemented and ran the [fixed-design POC](poc-count-models.md): fit 2021,
calibrate 2022, explore 2023 with five authority holdouts and matched one/two-year
feature cohorts. All six model/lag combinations completed, producing 12 raw/scaled
comparisons on 219 evaluation rows. Two-year raw ridge had the lowest errors;
boosting did not beat ridge and calibration harmed the two-year models. No
statistical superiority, operational timing validity or promotion is claimed.

Official release dates identify both feature and calibration-label timing risks.
The current calibration experiment cannot represent a genuine end-2022 forecast.
Prioritise as-of source/label availability and broader temporal evidence before
more model tuning. The app and its served retrospective layer are unchanged.

Real-data reruns produced the same prediction artifact SHA-256:
`02a612de1fbd0827788ee20769e63f56e577322731f1ffa7a3edfc413bb9df8c`.
Nineteen focused POC tests exercise calibration validation, exposure scaling,
geographic/identity exclusion, scoring-label independence and deterministic
end-to-end repeats with altered 2024 outcomes. Optional POC dependencies are
included in the backend CI install; remote CI has not run for these local changes.

## Presentation review, 8 September

Added a [model card](model-card.md) and [demo recording guide](demo.md), linked
from the README alongside the paired benchmark. Rechecked the six-decimal
future/authority test metrics against the generated ridge-Poisson report and
recorded its SHA-256 in the card. The failed lagged NB2 fit, worse calibration
ratio, unverified publication timing and unimplemented challengers remain explicit.

Corrected the architecture description: the working pilot serves GeoJSON and
Parquet through FastAPI, not national PMTiles or DuckDB snapshots. Roadmap next
steps now prioritise visual acceptance and recording before further model scope.
Fresh confirmatory geography/time is needed after using the existing test
results to guide improvements. No screenshots, recording, public deployment,
new model run or remote CI result is claimed by this documentation increment.

## Position against the plan

RoadSafe has reached the statistical core, but not model promotion. The local
official-data panel has 1,516 segment-year rows across 2019-2024 and five
authority codes. Ingestion, network matching, exposure joins, the rate baseline,
NB2 SPF, retrospective Empirical Bayes and an investigation UI exist. The next
step is defensible evaluation, not additional model complexity or a risk map.

## Current increment: joint geographic and temporal backtesting

Acceptance criteria:

- Train only on 2019-2022; report 2023 and 2024 separately.
- Exclude the scoring authority from every fitting step, including feature
  encoding and the exposure-rate baseline.
- Exclude scoring segment identities even if authority boundaries changed.
- Keep failed folds visible and compare models on identical completed rows.
- Do not promote a model without verified prior-period feature availability.

The existing `build-spf` command now produces this diagnostic alongside the
historical leave-one-authority-out benchmark. Regression tests check membership,
future-target independence, missing authority codes, overlapping periods,
single-authority scoring, empty fitting sets and partial-fit reporting.

## Real-data result

Run on 7 September 2026, using `configs/evaluation-v1.json` and the local
`data/processed/contract-v1/segment-year-panel.parquet`:

```bash
roadsafe build-spf \
  --panel data/processed/contract-v1/segment-year-panel.parquet \
  --contract configs/evaluation-v1.json \
  --output data/processed/contract-v1/spf-future-holdout
```

Four of five folds converged. The E08000032 fold did not converge and is excluded
from both models' aggregate metrics. Successful folds cover 443 of 517 future
segment-year rows: 224 validation and 219 test rows. These are partial benchmark
results, not evidence of performance on the complete pilot.

| Completed-fold metric | NB2 SPF | Exposure-rate baseline |
| --- | ---: | ---: |
| 2023 MAE | 0.507 | 0.567 |
| 2024 MAE | 0.503 | 0.548 |
| 2024 RMSE | 0.772 | 1.077 |
| 2024 observed/predicted count ratio | 0.593 | 0.656 |

Both models overpredict on these test rows. Statsmodels also emitted numerical
warnings during optimization. No optimizer fallback or post-hoc tuning was used
to turn the failed fold into a passing result. The machine-readable report
records input/contract checksums and fold-specific metrics; bulk data and
generated reports remain outside Git.

## Verification

- `make check`: Ruff lint/format, strict mypy and frontend TypeScript passed.
- `make test`: 71 Python tests and one frontend test passed.
- `npm run build` in `apps/web`: passed.
- `npm audit --audit-level=moderate`: zero vulnerabilities after compatible
  updates to Browserslist, Nano ID, PostCSS and their transitive dependencies.
- `git diff --check`: passed.

These checks validate the implementation, not the predictive adequacy of the
model. The nonconvergent fold and feature-timing limitations remain open.

## Next work, in order

Update: the next increment implemented the lagged feature panel, diagnosed the
NB2 zero-event-category failure, and evaluated a separate regularized Poisson
benchmark. See [the follow-on report](lagged-benchmark.md). The list below is
retained as the original handoff; publication-date verification and uncertainty
evaluation are still pending.

1. Build an explicit feature-availability contract and prior-year joins. Same-year
   AADF is not known at the declared prediction cutoff; prior-year values may
   also need publication-date checks or a longer lag.
2. Diagnose the nonconvergent training fold without using its future labels to
   select a remedy. Revisit sparse categories and model identifiability.
3. Define calibration thresholds, interval coverage and uncertainty on paired
   model differences. Precision now measures KSI-positive segment fraction;
   mean collisions per selected segment is a separate, explicitly named metric.
4. Evaluate a calibrated boosted-tree challenger using the same splits, then
   expand geography for external validation.
5. Add a public benchmark/model card and model-comparison UI only after the
   analytical gates pass. The existing descriptive/retrospective map remains
   separate from unpromoted forecasting experiments.

## RoadSafe investigation increment

Implemented a road-segment selector with map centring, clear selection and JSON
export. Selection resolves against current canonical features, avoiding tile-clipped
geometry and stale model fields. Missing, duplicate, wrong-year, mismatched-KSI or
invalid numerical retrospective records are not merged. Observed evidence and
exposure are never overwritten by retrospective records.

Live integration also exposed an older pre-contract network artifact without
stable segment keys. The demo now uses the contract-v1 network output; the UI
rejects missing or duplicate keys with an explicit rebuild message.

The API provides SHA-256 fingerprints of collision, network and optional EB
artifacts. Exports preserve those fingerprints, scope, licence and limitations.
The collision request now includes the complete current pilot rather than the
default first 500 records, and fatal severity has a filter and distribution entry.
Queued map-load callbacks are removed when their inputs change; mode visibility
is reapplied after source changes. Mobile search and selection are available.

Verification: 102 Python tests, 11 frontend tests, Ruff, mypy, TypeScript and the
production frontend build passed. Live API metadata identifies the 1,791-record
West Yorkshire pilot and all three artifact fingerprints. The corrected live
configuration has unique stable keys and matching retrospective records for all
256 road segments. Browser discovery
returned no available browser, so visual screenshots, tile rendering and physical
download verification are still pending; mocked interaction tests are not a
substitute for those checks. No public demo readiness or forecast promotion is
claimed. Changes remain local and unpushed.

Next: desktop/mobile browser review and a short observed -> exposure -> screening
-> retrospective -> export recording, followed by publication-date verification
and predeclared calibration/uncertainty gates for the forecasting benchmark.

## Other project handoffs

Updated 1 October 2026 after checking the project plans and local artifacts:

- RoadSafe UK: the retrospective investigation workflow already has local
  desktop/mobile screenshots and evidence-download checks; see [the demo](demo.md).
  Forecast promotion remains blocked on source vintages and derived-panel lineage.
  Prepare the descriptive demo independently of that research gate.
- ReWear AI: 200 original ABO images across 100 products are acquired with
  dimension and exact-pixel checks. Complete visual, near-duplicate and family
  review before the portable/OpenCLIP development benchmark. Do not describe
  fixture overlays as trained defect detection or category smoke tests as
  successful same-product retrieval.
- SpectraHeat UK: real optical COGs, Landsat acquisition/scaling/QA and a static
  diagnostic figure are implemented locally. Both tested thermal scenes fail
  the provisional 2 K uncertainty policy. The figure shows source uncertainty,
  not accepted temperature or heat-risk predictions. Review the uncertainty
  policy and multi-date data before training; HSI access remains unconfirmed.

## Portfolio delivery sequence

1. Finish each bounded increment with regression tests, provenance and an
   updated handoff; avoid simultaneous unverified model/UI changes across repos.
2. ReWear next: record a complete cohort review, freeze any score-independent
   exclusions, then run the two retrieval baselines on identical images. Preserve
   per-query failures and report development-only metrics before building results UI.
3. RoadSafe presentation: reproduce the full-pilot investigation, audit keyboard
   access and export, then prepare a serving bundle and a short recording. Public
   deployment and release-commit CI remain separate unchecked gates.
4. SpectraHeat: justify uncertainty acceptance before cohort selection, then build
   a measured-layer/QA inspector. Only later add evaluated model predictions.

These are evidence-based stages, not completion percentages. Profile/CV claims
must name implemented, tested capabilities and distinguish local demonstrations
from public deployments and research models from validated predictions. No new
public deployment or profile claim was made by this planning update.
