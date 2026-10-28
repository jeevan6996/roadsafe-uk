# Delivery roadmap

## 0.1 Data foundation

- reproducible DfT ingestion and quality report
- observed-evidence API and investigation map
- explicit source, licence, scope, and responsible-use caveats

## 0.2 Network and exposure (current)

- completed: year-aligned DfT major-road segment geometry
- completed: collision matching with distance and ambiguity diagnostics
- completed: AADF linkage, quality flags, and exposure coverage view
- deferred expansion: OS Open Roads geometry and a defensible minor-road exposure strategy

## 0.3 Statistical screening

- completed: stable count-point identity and authority/road-class metadata
- completed: longitudinal panel builder and evaluation-readiness report
- completed: auditable readiness score and check-level blockers
- completed: atomic official-source acquisition with provenance manifests
- completed: contract-level annual evidence orchestration command
- completed: observed exposure-normalized descriptive screening report
- completed: screening stability labels and transparent rate standard-error proxy
- completed: exposure-rate baseline with validation/test metrics
- completed: descriptive screening mode in the investigation map
- implemented: negative-binomial NB2 SPF benchmark with exposure offset and baseline comparison
- implemented: training-only Poisson-gamma Empirical Bayes retrospective screening with expected and excess frequency
- completed: ingest and match annual 2019–2024 collision/network evidence
- completed: join authoritative 2011 urban/rural classification for all contract years
- completed: run the SPF on the generated 2019–2024 panel with calibration, ranking, subgroup, and authority-holdout diagnostics
- current: retain the SPF as an evaluated benchmark; panel readiness and SPF reports expose authority overlap, and the SPF now evaluates every training authority in leave-one-authority-out folds; it remains unpromoted because the current panel has no genuinely unseen future authorities
- implemented: joint future-year/leave-one-authority-out evaluation, excluding each scoring authority and its stable segment identities from fitting; partial real-data results are recorded in [the progress report](progress-2026-09.md)
- implemented: exact-year lagged feature panel with exclusion artifacts and provenance; prediction-year covariates are excluded from the model design
- evaluated: separate ridge-Poisson benchmark on the lagged real panel; all five future/authority folds fit, while unpenalized NB2 remains nonconvergent (see [benchmark](lagged-benchmark.md))
- next: verify publication-time feature availability and define calibration/uncertainty acceptance criteria, then repeat promotion evaluation; expand geography for external validation
- next: compare SPF and Empirical Bayes with calibrated ML challengers using temporal and geographic backtests with uncertainty intervals

## 0.4 Model agreement

- explored: optional Poisson-boosting and multiplicative-calibration POC on paired
  one/two-year lag cohorts; neither implies promotion (see [results](poc-count-models.md))
- next analytical gate: publication-aware inputs and calibration labels, more
  historical fitting years and fresh geographic evaluation
- implemented: source-availability preflight with cutoff checks and local vintage
  hash verification; archived sources and derived-panel lineage remain pending
  (see [audit](source-availability.md))
- implemented: source-audited POC bundles, blocking before fitting by default,
  explicit exploratory overrides, artifact fingerprints and failure reports;
  passing source checks still does not certify panel lineage or promotion
- pending: accepted calibrated boosted-tree challenger
- emerging-pattern detector
- shared ranking, calibration, stability, and subgroup evaluation
- agreement and disagreement representation in the product

## Next delivery: pilot demonstration

- implemented: selected-road evidence export with source fingerprints and limitations
- documented: [model card](model-card.md), failed experiments and paired benchmark results
- documented: [recording storyboard and visual acceptance checklist](demo.md)
- verified locally: Chromium desktop/mobile workflow, evidence download and real screenshots
- implemented: portable, hash-verified fixture/pilot serving bundles with frozen API snapshots
- verified locally: selected-state semantics, visible search focus, and keyboard
  investigation/export at desktop and 320-pixel width
- implemented: reproducible production capture with evidence checks and media hashes;
  encoded-frame review is a separate acceptance step
- pending: full accessibility audit, additional browser engines and recording publication
- keep descriptive and retrospective evidence available without implying forecasting promotion
- add model-agreement and disagreement views after the promotion gate passes
- pending: a public read-only deployment with reproducible serving artifacts and smoke checks

## 1.0 Defensible investigation workflow

- persisted investigations; per-selection evidence export is already implemented
- model and data cards linked from every analytical layer
- automated end-to-end and visual regression coverage
- national-scale batch pipeline with reproducible release artifacts

## Immediate sequence

1. Record the browser-verified pilot using the verified serving bundle, then
   prepare a read-only public demonstration with release-commit CI and smoke checks.
   Validate generalized network geometry and matching sensitivity before making
   stronger location-specific claims; retain current exclusions explicitly.
2. Verify feature publication-time availability and predeclare calibration and
   uncertainty gates. Reserve fresh geography or time for confirmatory evaluation
   because the existing test results have already informed the next steps.
3. Evaluate a calibrated challenger only after those gates are defined; add
   agreement/disagreement visuals only when supported by accepted evidence.

Do not expand the model list or road coverage at the expense of these gates.
