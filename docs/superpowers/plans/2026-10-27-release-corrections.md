# RoadSafe Review Corrections Implementation Plan

> **For agentic workers:** Use superpowers:executing-plans for local execution and independent review of the final integrated changes. Follow red-before-green regression testing.

**Goal:** Correct the verified data-integrity, analytical-contract and UI findings before release.

**Architecture:** Retain the existing batch/serving/UI boundaries. Validate inputs at their producers and verify cross-artifact consistency at serving. Keep forecasts unpromoted and all work local.

**Tech Stack:** Python, Polars, Pydantic, FastAPI, React, TypeScript, MapLibre, pytest, Vitest, Playwright.

**Spec:** The current known gates and bounded correction evidence are recorded in
[`../../progress-2026-10.md`](../../progress-2026-10.md). The original detailed
review is retained outside the repository in the author's local audit workspace.

## Global Constraints

- No commits, pushes or public uploads without specific approval. The author
  approved publishing a reviewed experimental progress milestone on 28 October;
  this does not mean the remaining tasks are complete or authorise deployment.
  On 31 October the author requested further tested personal-project milestones
  and pushes; this authorises the reviewed consistency increment, not deployment
  or model promotion.
- Preserve existing local work and raw/generated data exclusions.
- Do not choose uncertainty semantics implicitly. Await the user's latent-versus-predictive choice.
- Model promotion and historical-source lineage remain separate gates.

## Review Focus

- Null/nonfinite/fractional count values must not become valid-looking zero targets.
- Equivalent CSV and Parquet inputs must receive equivalent identity validation.
- Bundle summaries/rates must not contradict their collision and exposure evidence.
- A filtered-out selection and a partial API failure must not misrepresent observed evidence.
- Regenerated artifacts, serving fingerprints and media must refer to the same revision and uncertainty contract.

## Tasks

- [x] Ingestion: reproduce null severity and duplicate-Parquet aggregation, fix producer validation, test both formats and existing network behavior.
- [x] Analytical validation: reproduce invalid EB/readiness success; require finite positive exposure and finite nonnegative integral counts, reject invalid outputs before writing successful artifacts. Include the directly callable exposure baseline and integer export contract; evidence is in the October progress log.
- [x] Bundle: reject impossible totals and inconsistent rate/exposure values while preserving explicitly allowed matching exclusions and rounding precision.
- [ ] Uncertainty: resolve the user choice, add equation regressions, update the producer/consumer/documentation contract and regenerate into fresh output paths.
- [ ] UI: clear hidden collision selections; split observed/network request states with retry; use explicit rate/KSI units; add selected-road highlighting and numeric legends with regression coverage.
- [ ] Dependencies: refresh only affected compatible packages, inspect lockfile, rerun full and production-only audits.
- [ ] Verification: full Python 3.12 tests/lint/types, frontend tests/types/build, real-pilot browser tests and screenshots, fresh real-data artifacts where affected.
- [ ] Review: independent integrated review; resolve substantive findings and record limitations before publication approval.

## Completion Evidence

Record actual failing/passing commands and counts in the progress log. A pending
scientific decision, unavailable browser or untested deployment is not passed.
Refresh screenshots/video only after the final verified artifact choice; retain
previous evidence rather than overwriting it.
