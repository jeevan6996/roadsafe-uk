# October 2026 execution review

## Release corrections and final local checks, 27 October

Independent review found gaps that the initial green checks below did not cover:
SPF predictions could pass bundle identity checks and be labelled retrospective
EB; malformed serving values could pass verification then fail API requests;
legacy cached reads could be paired with hashes of replacement files. A separate
analytical review found reused POC directories could retain stale predictions
and the standalone CLI could exit successfully despite incomplete experiments.

Added red-before-green regressions and corrected these boundaries. Serving
validation now shares the collision conversion, checks network fields/geometry
and requires distinct EB fields and retrospective semantics. The API projects
only validated retrospective fields. Both configuration modes snapshot and hash
the same bytes at startup. The frontend response type matches the projected
contract. Standalone POC output requires a fresh directory and incomplete runs
exit nonzero with an explicit partial status.

Final verification on the corrected local tree:

- 195 Python tests passed in an isolated Python 3.12.14 environment installed
  from `.[dev,poc]`; this is a local macOS run, not Ubuntu Actions CI.
- Python 3.12 Ruff lint/format and strict mypy passed (19 source files).
- 16 frontend tests, frontend/E2E TypeScript and production build passed.
- Eight production-browser tests passed against the restarted corrected pilot
  API, using Node 24 and installed Chrome through the local-only runner config.
  Desktop and 320-pixel retrospective screenshots were inspected for readable
  panels, evidence layers and visible attribution. Artifacts remain ignored in
  `output/playwright/release-final-2026-10-27/`.
- Existing pilot bundle reverified unchanged: 1,791 collisions and 256 links.
- All six real-data POC experiments completed in a fresh directory and reproduced
  the documented rounded metrics; see the POC report for its new fingerprint.
- Final cross-review by two agents found no remaining blockers in the corrected
  serving/API/frontend contract and POC areas. These bounded reviews are not a
  certification of historical source lineage or every original project feature.

The Python 3.12 suite emitted 78 Shapely transformation deprecation warnings
and one joblib physical-core-detection warning. They were not failures. Browser
execution also emitted the existing FORCE_COLOR/NO_COLOR warning. Node 22, other
browser engines, public deployment, full accessibility and remote CI remain
unverified at this checkpoint. No release commit, push, public recording upload
or model promotion was performed. The earlier recorded video was not regenerated
or human-approved here.

Next: prepare the reviewed local release revision for approval, publish it only
after approval, inspect that exact head's CI, then publish accepted demo media
and select read-only hosting. Do not reopen model expansion ahead of delivery.

## Release verification checkpoint, 27 October

Rechecked the current local working tree, based on commit `a7955dd`. The pending
changes include analytical experiments, serving bundles, frontend evidence export,
browser tests and demo documentation. This checkpoint is not a full review of
that combined diff, a committed release, or remote CI evidence.

Fresh commands, run from the repository root unless noted:

| Command | Result |
| --- | --- |
| `.venv/bin/pytest` | 162 passed; one nonfatal physical-core-detection warning |
| `.venv/bin/ruff check .` | Passed |
| `.venv/bin/ruff format --check .` | 35 files already formatted |
| `.venv/bin/mypy src` | Passed, 19 source files |
| `npm run check` from `apps/web` | Frontend and E2E TypeScript passed |
| `npm test -- --run` from `apps/web` | 15 tests passed |
| `npm run build` from `apps/web` | Passed; MapLibre worker asset emitted |
| `git diff --check` | Passed for the tracked diff |
| `.venv/bin/roadsafe verify-demo-bundle --bundle data/processed/demo-bundle-2026-10-13` | Passed; 1,791 collisions and 256 links |

Bundle collision, network and retrospective hashes match the fingerprints in the
demo runbook. Existing recording files and capture/visual-review JSON are present
in the ignored October 23 output directory. Browser tests, frame inspection and
recording were not rerun at this checkpoint. The local Python environment is
3.14; this does not verify the workflow's Python 3.12 environment.

Release sequence:

1. Review all tracked and untracked release files against the base, including
   experiment-to-serving boundaries and artifact/licensing exclusions. The passing
   checks above do not substitute for this review.
2. Rerun production-browser acceptance on the intended release tree, preserving
   real pilot inputs, attribution and evidence-export checks.
3. Prepare a coherent release commit, obtain approval for its publication and
   inspect CI on that exact published head. No commit or push was made here.
4. Obtain human acceptance of the recording, publish it with release provenance,
   then select hosting and perform public read-only deployment smoke tests.

Keep the release descriptive and retrospective. Forecast promotion remains
blocked by publication-aware feature lineage and calibration/uncertainty gates.
Do not add more models before delivering the bounded investigation demo.

## Local readiness review, 23 October

Revalidated the current uncommitted tree: 162 Python tests and 15 frontend tests
passed. Ruff lint/format, strict mypy (19 source files), frontend/E2E TypeScript
and whitespace checks passed. The frontend production build also passed,
including emission of the MapLibre worker asset. The existing 2024 pilot bundle independently
verified again: 1,791 collision records, 256 links and unchanged artifact hashes.
Eight real-pilot browser acceptance tests also pass against the production build,
including full keyboard investigation/export at desktop and 320-pixel width.
Production screenshots were refreshed and inspected at desktop/mobile sizes.
The physical-core-detection warning remains nonfatal.

The targeted keyboard milestone now exposes selected mode/filter state and
restores search focus visibility. The independent review found no blockers in
that increment; it did not review the entire older uncommitted tree. The capture
script also received independent review, with timeout, cleanup and completion-
status corrections verified before use.

A silent 86.44-second, 1440 x 900 production-demo capture completed with no page
errors, 107 successful tile responses, canonical evidence-download validation,
entry-asset hashes and the verified pilot fingerprint. Four sampled encoded
frames and the final frame were inspected for evidence layers, attribution,
footer and readable panels. WebM and a 5.4 MB H.264 MP4 remain locally ignored in
`output/playwright/production-demo-2026-10-23/`, with capture and visual-review
JSON. This is a sampled agent inspection, not human approval of every frame.

Initial CLI/installed-Chrome recordings cropped the footer and were rejected.
The macOS Chrome backing-window correction was verified on actual encoded frames.
One matching Chromium 145 attempt reported a fragment-shader compilation error;
an unchanged control passed. That version is not certified by this milestone.
The accepted paced run used Chrome 155 with Node 24; the browser-installer stall
under Node 26 and older-browser failure remain explicit tooling limitations.
Fresh-directory reuse and an invalid source API both fail without a successful
completion manifest. Capture completion itself never asserts visual acceptance.

Next, review and publish a coherent release revision and inspect that revision's
CI before attaching the accepted recording publicly. Public deployment still
requires hosting and smoke checks. Keep the demo
descriptive/retrospective; publication-aware forecasting inputs, calibration and
uncertainty criteria remain separate analytical work. Do not add more models
before delivering the existing investigation workflow.

These results apply to the local working tree, not the September 2 published
revision. No public release, public recording, deployment or new forecasting validation is
claimed by this review.

## Verified serving and browser milestone, 13 October

Implemented `build-demo-bundle` and `verify-demo-bundle` for the bounded 2024
fixture and pilot. Bundles copy the serving artifacts, verify SHA-256 checksums,
year, unique identities, counts and retrospective alignment, then publish a
completion manifest. Existing output directories are rejected. Failed builds
can leave an incomplete directory but never a completion manifest.

The API accepts `ROADSAFE_BUNDLE_PATH`, rejects mixed individual-path
configuration, and freezes loaded artifacts and metadata together after
verification. `/api/v1/release` reports the manifest fingerprint and application
version. Changes on disk require a verified restart. Integrity checks do not
certify original-source authenticity, feature vintage or model promotion.

Browser validation reproduced a missing MapLibre 6 worker: the basemap rendered
but the worker returned 404, so collision and road evidence never initialized.
The official Vite setup now supplies a bundled `?worker&url` worker before map
construction. Evidence initialization follows `style.load`; screenshot readiness
still follows real map idle, with no timeout-based readiness shortcut.

Validation:

- 162 Python tests and 13 frontend tests passed.
- Ruff lint/format, strict mypy (19 source files), frontend/E2E TypeScript and
  `git diff --check` passed.
- The real 1,791-collision/256-link bundle passed independent CLI verification.
- All three Chromium acceptance tests passed against development and production
  builds: desktop export plus 390- and 320-pixel mobile workflows.
- Production screenshots were inspected for evidence overlays, attribution and
  readable narrow-screen layout, then refreshed in `docs/media/`.
- The production build emits a self-contained MapLibre worker asset.

The existing physical-core-detection warning and Node deprecation warnings are
nonfatal. These are local results from an uncommitted tree, not remote CI or a
published release. No public deployment, recording or forecast promotion is
claimed. The [demo runbook](demo.md) records commands and artifact fingerprints.

## Skill-guided execution

Use skills for their relevant work, not as substitutes for project evidence:

| Work | Skill/tool | Completion evidence |
| --- | --- | --- |
| UI inspection and interaction | Browser skill; Playwright workflow when no connected browser exists | Real-data desktop/mobile screenshots and export verification |
| New exploratory notebooks | Jupyter notebook skill | Reproducible cohort, fixed experiment design and executable results |
| GitHub Actions failures | gh-fix-ci skill | Failure-log diagnosis and explicitly approved, locally checked correction |
| Public Render deployment | render-deploy skill when hosting is selected | Reviewed deployment configuration and public smoke tests |
| Explicit security review | security-best-practices skill | Scoped findings and regression checks for supported languages |

No connected in-app browser was available, so this milestone used the
repository's existing Chromium acceptance suite. The suggested Hugging Face
plugin remains unconnected; it is not a prerequisite or an installed capability.
Do not provision accounts or paid hosting implicitly.

## Next bounded increments

1. RoadSafe: targeted keyboard review and a local silent recording are complete;
   review the complete pending release, prepare a clean commit, then verify its
   actual CI before publishing media or deploying. Full accessibility remains open.
   Publication-dated source vintages, derived-panel lineage and predeclared
   calibration/uncertainty criteria remain separate analytical blockers.
2. ReWear: complete visual, family and near-duplicate decisions for the acquired
   ABO images before freezing a score-independent development cohort. Compare
   the portable baseline and OpenCLIP on identical queries, preserve failures
   and measure latency on this machine before building the retrieval results UI.
3. SpectraHeat: justify the thermal uncertainty policy and inspect multiple dates
   before model training. Build an optical/thermal QA inspector that distinguishes
   accepted measurements from rejected pixels and missing coverage; do not label
   source uncertainty as a model confidence interval or claim HSI access.

Work one increment at a time. Update the relevant model/data card, tests,
runbook and screenshots when behavior changes. Claims on the profile or CV must
distinguish local demos, deployed applications and validated modelling results.

## 27 October: ingestion release correction

Completed the first task in the [release-corrections plan](superpowers/plans/2026-10-27-release-corrections.md).
CSV and Parquet now share the collision reader's required-column, identity and
severity checks. Null severity is explicitly invalid. Network builds no longer
bypass validation for Parquet, preventing duplicate IDs from multiplying joins
and missing severity from silently reducing KSI counts.

Before implementation, the network regressions reproduced three missing-rejection
failures: duplicate Parquet IDs and missing severity in CSV/Parquet. New tests
also cover invalid severity, format equivalence and rejection before output
artifacts are created. Thirty targeted tests and all 209 Python tests pass on
Python 3.14.7 / Polars 1.42.1. Scoped Ruff lint/format, strict mypy across 19 source
files and diff-whitespace checks pass. One non-failing joblib CPU-detection
warning remains. Python 3.12 and remote CI were not rerun for this revision.

An independent read-only review traced the pilot producer, matching/join path,
CLI callers and evidence consumers, reproduced the original three failures from
HEAD in memory, and reported no actionable findings in this bounded correction.
No commits, pushes, artifact regeneration or updated media are part of this step.
The unresolved uncertainty decision and remaining release findings stay open.

The existing pilot bundle still verifies at 1,791 collisions and 256 links. The
local API was restarted with that bundle; it reports retrospective data available.
Reload the frontend after restoring the API. The new [usage guide](usage.md)
explains the working modes and intentionally disabled planned views.

## 28 October: analytical numeric correctness gate

Completed the second release-corrections task, without changing the unresolved
EB uncertainty formula. Readiness now blocks non-finite/non-positive exposure,
non-finite/negative/fractional counts and nonnumeric types. Both EB and the
exposure baseline independently validate training/scoring inputs, reject
non-finite derived values and serialise reports as strict JSON before creating
success outputs. No new predictive capability or accuracy gain is claimed.

Implementation decisions recorded during execution:

- Included the baseline because its directly callable CLI path shared the same
  validation gap and could bypass a corrected readiness report. Leaving it
  unchanged would leave a misleading successful-artifact path.
- Preserved Decimal support: the original implementation accepts numeric Decimal
  inputs, but Polars `is_finite` does not operate directly on that dtype.
  Finiteness uses a floating view; exact positivity and integrality comparisons
  retain the original values so large fractional Decimals are not rounded valid.
- Standardised scoring count artifacts to `UInt64`. Integer-valued floats are
  valid counts but previously failed strict `RetrospectiveRecord` validation.
  Unrepresentable counts are now blocked consistently rather than failing later
  during conversion or publication. This intentionally changes the count dtype;
  it does not change valid observed counts or model estimates.

Regression evidence:

- Initial readiness/EB regression run: 24 failures before implementation.
- Baseline expansion: 16 failures before implementation; final baseline tests
  against the original HEAD implementation produce 19 failures.
- Review reproductions covered Decimal operation failures and strict-integer
  consumer failures; their regression tests failed before the corrections.
- Range regressions reproduced five failures at `2**64` before range checks.
- Final checks: 107 targeted tests and all 299 Python tests pass; Ruff lint and
  formatting, strict mypy across 19 source files and diff-whitespace checks pass.
- One existing non-failing joblib physical-core-detection warning remains.

Real-data compatibility was checked using temporary output directories. All 517
EB scoring rows match the existing artifact's count and numeric estimate values,
and all pass the strict serving record model. All 517 baseline rows and its
split metrics match the pre-correction HEAD implementation. Both report paths
produce strict JSON. Temporary verification artifacts were not added to the
serving bundle or committed.

An independent read-only review found a Decimal compatibility regression in the
initial revision, then verified the corrected six-file implementation and its
tests with no remaining actionable findings in scope. Additional reviewer probes
rejected exact fractions beyond Float64 precision and `2**64`, and accepted
`UInt64.max`. These checks prove bounded software contracts, not scientific
validation of the retained uncertainty proxy.

Environment: Python 3.14.7 / Polars 1.42.1. Python 3.12, remote CI and new browser
checks were not run for this batch-only correction; the frontend was unchanged.
No commits, pushes, persistent artifact regeneration or updated media are part
of this milestone. Bundle consistency, the user's uncertainty choice, remaining
UI corrections and calibration/promotion gates remain open.

## 28 October: road-focused investigation milestone

Selected roads now have a distinct outline and dimmed surrounding links. Road
focus persists across evidence modes, and the matched-point list supports
severity filtering, keyboard selection, collision details and restoring network
context. Source snapshot mismatches and stale asynchronous responses fail closed.
The Observed footer reports the points actually displayed during road focus,
not the whole area's collision total.

The new read-only endpoint derives assignments from frozen canonical geometry
using the existing BNG matching rules. It validates every link's collision and
KSI counts before returning locations. Independent verification queried all 256
roads and compared exact identities with saved assignments and a fresh raw-BNG
shapefile match: 330 accepted collisions and 76 KSI collisions, with no assignment
differences. Geometry remains generalised; matching is not lane-level proof.

Review findings corrected before publication:

- Typed-date Parquet pilot inputs now preserve dates instead of applying string
  parsing; unsupported date dtypes fail cleanly. Two regressions failed before
  the correction and passed afterward.
- Versioned API replies now expose one frozen snapshot identity. The client
  checks the essential data group before loading and only combines optional
  metadata/EB responses from that same snapshot. Two backend header/identity
  tests and mixed/missing-snapshot browser-unit regressions failed before fixes.
- The retrospective browser fixture now includes its year and a valid retained
  variance-proxy value; it asserts displayed expected values. Its prior run
  failed with a missing expected value, rather than proving model integration.
- Initial frontend follow-up regressions produced 15 failures before fixes;
  final unit checks pass. Current dependency audits report zero vulnerabilities
  for both full and production-only installs after compatible patch updates.

Final local verification used a fresh Python 3.12.15 environment with the declared
`dev,poc` extras: 318 tests pass with 90% coverage, Ruff lint/format and strict mypy
across 20 source files pass. Dependencies include Polars 2.1.0, statsmodels 0.15.0,
Shapely 2.2.0 and Pydantic 2.14.1. Shapely transform deprecations and one joblib
CPU-detection warning remain non-failing. These are not newly rerun model-quality
benchmarks; historical result tables retain their recorded experimental scope.

On Node 24, frontend/E2E type checks, 42 unit tests and the production build pass.
All 15 installed-Chrome acceptance tests pass against actual `/assets/` production
entry files: 11 real-pilot tests and four synthetic failure/renderer fixtures.
New desktop and mobile captures in `docs/media/focused-road-*` were visually
inspected for visible geometry, collision markers, readable details, attribution
and non-overlapping controls. Node colour/deprecation warnings are non-failing.

Runtime/data and frontend review passes identified and checked the bounded
corrections above. A fresh additional whole-model review could not run because
the selected review model was unavailable; that pass is not claimed as completed.
The earlier analytical review and current tests do not replace outstanding
scientific validation. Publication is an experimental progress milestone, not a
validated safety-model release. Remote CI must be checked on the pushed head.

Bundle cross-artifact rate/total consistency remains a known open task. The new
point endpoint withholds inconsistent assignments, but this does not certify
every other endpoint's analytical consistency. EB uncertainty semantics, partial
network-error recovery, source-vintage lineage, calibration, external validation,
public deployment and recording publication also remain open.

## 31 October: internally consistent serving evidence

Completed the bounded aggregate/rate task in the release-corrections plan.
Bundle construction, verification and legacy API startup now reject matched
collision, KSI or non-KSI totals exceeding the corresponding source population.
Valid matching exclusions remain allowed: the 12-record fixture still has only
two accepted matches. Per-link rates must agree with counts and positive finite
exposure, including optional annual vehicle-km. The producer's 365-day convention,
100-million vehicle-km rate scale and four-decimal fixture rounding are retained.
Contradictions are rejected, never silently corrected or hidden by fresh hashes.

Fourteen regressions failed before the change; two positive controls passed.
Coverage includes impossible totals, zero/overflowed exposure, finite inputs
producing a nonfinite rate, wrong or ill-typed annual vehicle-km, inconsistent
rates, altered artifacts with recomputed hashes, and legacy startup rejection.
The matching tests' synthetic inputs changed counts but retained copied zero
rates; their fixture construction now recalculates rates. Their intended spatial
mismatch/cache assertions remain, including explicit canonical-assignment failure.

Independent review found a valid half-step rounding value that exceeded the
absolute tolerance by floating-point roundoff. Its new regression failed before
adding one ULP of boundary allowance; an actually inconsistent neighbouring rate
remains rejected. This does not broaden the intended four-decimal precision.

All 336 Python tests pass on Python 3.12.15 with current declared dependencies.
Ruff lint/format and strict mypy across 20 source files pass. Shapely transform
deprecations and the existing joblib CPU-detection warning remain non-failing.
The unchanged real serving bundle verifies with 1,791 source collisions and
256 links, without rewriting its collision/network/retrospective artifacts.
Remote CI is checked separately after the milestone push.

This is a software evidence-consistency milestone, not a model-quality gain or
scientific validation. Per-road spatial assignment reconstruction remains a
separate point-endpoint gate. EB uncertainty semantics, partial API recovery,
source-vintage lineage, calibration, external validation, deployment and the
public recording remain open; no new model or training result is claimed.
