# RoadSafe UK

Exposure-aware road safety screening for Great Britain, designed to show where
historical evidence, professional statistical methods, and calibrated machine
learning agree or disagree.

> **Current state: experimental working pilot / work in progress.**
> The local investigation workflow has desktop/mobile screenshots and keyboard
> investigation/export checks. This is a progress milestone, not a validated
> forecasting model or a production safety tool. Public recording and deployment
> remain pending.
> A portable, hash-verified serving bundle is available for reproducible local runs.
> The application displays observed 2024 collision evidence, DfT traffic
> exposure, and exposure-normalised screening signals for major-road links. It
> does not publish expected-risk scores or intervention advice.

## Start here

[![Selected A61 road and matched collision investigation](docs/media/focused-road-desktop.png)](docs/demo.md)

Actual pilot data: selected A61 count point 16576, its spatially matched
collisions and one collision's details. This is an investigation example, not a
risk ranking. [Mobile view](docs/media/focused-road-mobile-390.png).

- [Demo walkthrough, keyboard checks and reproducible recording](docs/demo.md)
- [Using the interface and understanding disabled controls](docs/usage.md)
- [Model card: results, failed experiments and limitations](docs/model-card.md)
- [Reproducible lagged-feature benchmark](docs/lagged-benchmark.md)
- [Calibration, lag and Poisson-boosting POC](docs/poc-count-models.md)
- [Publication and source-vintage audit](docs/source-availability.md)
- [Source-audited experiment bundles](docs/source-availability.md#run-a-source-audited-experiment-bundle)
- [Architecture: implemented versus planned](docs/architecture.md)
- [Latest validation and execution handoff](docs/progress-2026-10.md)

The working application connects 1,791 West Yorkshire collision records to a
256-link major-road network, shows observed/exposure/retrospective evidence and
exports a selected link with source fingerprints. It is not a deployed national
forecasting service.

### Outstanding release gates

Bundle verification checks aggregate collision totals and count/exposure/rate
consistency, including rounded fixture values. This is not independent validation
of spatial assignments, model provenance or forecasting quality.

The Empirical Bayes uncertainty field remains an unvalidated proxy pending its
mathematical contract correction. Independent network/observed error recovery
and remaining UI corrections are tracked in the
[release-corrections plan](docs/superpowers/plans/2026-10-27-release-corrections.md).
Historical feature publication dates, derived-panel lineage, calibration and
fresh external validation still block predictive-model promotion. Working
software and local tests do not close those scientific gates.

### What actually works

| Approach | Evidence | Product status |
| --- | --- | --- |
| Exposure-rate baseline | Evaluated on held-out years and authorities | Benchmark; observed exposure-normalized rates are displayed separately |
| Poisson-gamma Empirical Bayes | Generated retrospective estimates matching all 256 current pilot links | Optional retrospective map layer |
| Ridge-Poisson SPF with lagged features | All five future/authority folds completed; test MAE 0.513 vs baseline 0.567, RMSE 0.789 vs 1.106 | Experimental, not served |
| Unpenalized NB2 SPF | Implemented and evaluated; lagged fit did not converge with a zero-event category | Failed lagged experiment, not promoted |

Those paired error metrics use 254 retained 2024 segment rows. Ridge-Poisson's
observed/predicted count ratio is 0.668: ranking and point errors improved, but
calibration is still inadequate. A separate 2023 exploratory Poisson-boosting
POC is now implemented but did not outperform ridge on that cohort. Graph models,
hierarchical Bayesian modelling and model-agreement views remain planned.

The contribution is an auditable investigation workflow: explicit matching
exclusions, traffic-exposure context, exact-year feature snapshots, geography
and time holdouts, and evidence exports. The statistical methods are established;
no novel algorithm or causal safety benefit is claimed.

## Why this project

Existing collision maps are useful for exploring reported events. RoadSafe UK
is being built for a different question: which road segments warrant further
investigation after accounting for traffic exposure, comparable roads,
uncertainty, and model disagreement?

The project will benchmark transparent historical and exposure-adjusted
baselines against Safety Performance Functions, Empirical Bayes screening,
hierarchical Bayesian models, boosted trees, emerging-pattern detection, and
road-network graph models.

## Current vertical slice

- provenance-aware ingestion of the official DfT collision CSV
- atomic, checksum-verified acquisition of official inputs for final 2019-2024 collision years
- schema, coordinate, duplicate-key, and severity validation
- reproducible West Yorkshire pilot extraction to Parquet
- machine-readable data quality report
- collision-to-link matching with distance and ambiguity diagnostics
- exact DfT count-point to AADF exposure joins with method quality flags
- stable count-point keys and local-authority/road-class metadata for longitudinal analysis
- segment evidence in Parquet and GeoJSON
- contract-aware segment-year panel construction with explicit readiness blockers
- contract-level annual evidence orchestration across all evaluation years
- observed screening stability labels and a transparent Poisson rate standard-error proxy
- transparent exposure-rate baseline with validation/test evaluation metrics
- experimental negative-binomial NB2 Safety Performance Function benchmark with exposure offset
- auditable Poisson-gamma Empirical Bayes retrospective screening with excess-frequency signals
- versioned FastAPI endpoints for collision and major-road evidence
- React and MapLibre observed/exposure investigation modes
- React and MapLibre exposure-adjusted screening mode with rate-based styling
- keyboard-accessible road selection and JSON evidence export with source fingerprints
- focused road outlines, dimmed network context and severity-filtered matched collision locations
- snapshot-bound browser loading and fail-closed road/point evidence alignment
- portable serving bundles with startup integrity checks and a release metadata endpoint
- future-year and grouped-authority evaluation contract
- fixture-driven unit and API tests

The full pilot contains 256 major-road links with 2024 AADF. Of 1,791 pilot
collisions, 330 are accepted within 50 metres, 61 are ambiguous, and 1,400 are
outside the major-road matching scope. These exclusions are a product feature,
not missing values to conceal or automatically impute.

## Quick start

```bash
python3.12 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[dev]'
pytest

uvicorn roadsafe.api.app:app --reload
```

In a second terminal:

```bash
cd apps/web
npm install
npm run dev
```

Open `http://localhost:5173`. The API is available at
`http://localhost:8000/docs`.

To serve a generated pilot instead of the 12-record test fixture:

```bash
ROADSAFE_DATA_PATH=data/processed/pilot-collisions-2024.parquet \
ROADSAFE_NETWORK_PATH=data/processed/contract-v1/segment-evidence-2024.geojson \
ROADSAFE_EMPIRICAL_BAYES_PATH=data/processed/contract-v1/empirical-bayes/empirical-bayes-screening.parquet \
  uvicorn roadsafe.api.app:app --reload
```

The optional Empirical Bayes path enables the `Retrospective` investigation mode;
without it, the mode remains unavailable rather than showing incomplete model
evidence.

### Investigation workflow

Select **Exposure** or **Screening**, search for a road, then choose a count point
in **Road segment**. The map centres on the link and the evidence panel displays
its observed counts and traffic estimation method. **Export evidence** downloads
the canonical geometry, observations, exposure, optional retrospective estimates,
limitations and SHA-256 fingerprints of the served artifacts. Export is disabled
without selection or source metadata.

Retrospective records must uniquely match the segment, year and observed KSI
count, with finite nonnegative estimates. They never replace observed road or
exposure fields. The export is an investigation record, not a prediction or
intervention recommendation. The collision view requests up to 5,000 records,
covering this 1,791-record pilot; larger deployments require pagination.

Desktop/mobile Chromium checks and real evidence downloads pass locally. See
[the captured workflow](docs/demo.md#verified-local-screenshots); a public recording
and deployment remain pending. The generalized DfT links are not precise road
traces, and matching exclusions must remain visible. See
[the progress handoff](docs/progress-2026-09.md) for verification and model gates.

## Acquire official source data

Fetch final annual collision and major-road inputs plus the shared AADF archive:

```bash
roadsafe fetch-sources \
  --years 2019 2020 2021 2022 2023 2024 \
  --output data/raw
```

Use `--kinds collision`, `--kinds roads`, or `--kinds aadf` for a selective
download. Existing artifacts are reused only when their URL, byte count, and
SHA-256 agree with the adjacent manifest; `--refresh` forces retrieval.
Downloads are written atomically, and each manifest records the official
source page, reporting period, publication status, licence, retrieval time,
size, checksum, and validation result. Bulk inputs remain excluded from Git.
DfT no longer offers 2019 as a standalone annual collision file, so requesting
2019 acquires and validates the substantially larger 1979–latest historical
collision file. Years 2020–2024 use the smaller annual publications.

## Build the pilot dataset

After acquisition, build a year-specific collision pilot:

```bash
roadsafe build-pilot \
  --source data/raw/dft-road-casualty-statistics-collision-2024.csv \
  --output data/processed
```

The command writes a pilot Parquet file and quality report. Raw and processed
datasets are intentionally excluded from Git.

## Build network and exposure evidence

Extract the acquired Major Roads Database and AADF archives, then run:

```bash
roadsafe build-network \
  --collisions data/processed/pilot-collisions-2024.parquet \
  --roads data/raw/MRDB_2024_published.shp \
  --aadf data/raw/dft_traffic_counts_aadf.csv \
  --output data/processed \
  --year 2024
```

The command writes accepted/rejected matches, segment evidence, serving
GeoJSON, and a quality report. AADF-derived rates are descriptive and remain
separate from future expected-frequency models.

## Build the evaluation panel

After building annual evidence for every contract year, combine the artifacts
without training a model:

```bash
roadsafe build-panel \
  --evidence data/processed/segment-evidence-{2019,2020,2021,2022,2023,2024}.parquet \
  --contract configs/evaluation-v1.json \
  --output data/processed
```

This writes `segment-year-panel.parquet` and
`panel-readiness-report.json`. Readiness requires all declared years, valid
exposure and targets, unique segment-year records, and complete subgroup
fields. It also requires at least one validation or test authority that is
absent from training. The current 2019–2024 West Yorkshire panel is therefore
blocked for geographic holdout evaluation until additional unseen-authority
evidence is added; modelling must still respect the documented
descriptive-exposure limitations.

Build an observed, exposure-normalized screening artifact from a ready panel:

```bash
roadsafe build-screening \
  --panel data/processed/segment-year-panel.parquet \
  --output data/processed
```

This writes `segment-descriptive-screening.parquet` and
`descriptive-screening-report.json`. The output ranks observed rates per
million vehicle-km and subgroup summaries only; it also labels low-count or
low-exposure estimates for cautious interpretation and includes a simple
Poisson rate standard-error proxy. It is not an expected-frequency or causal
model.

Evaluate the first model baseline after building a complete panel:

```bash
roadsafe build-baseline \
  --panel data/processed/segment-year-panel.parquet \
  --contract configs/evaluation-v1.json \
  --output data/processed/baseline
```

This estimates one KSI rate from training years, applies the annual vehicle-km
exposure offset, and reports validation/test MAE and RMSE. It is a transparent
benchmark for later Safety Performance Functions, not a deployment model.

Evaluate the experimental negative-binomial Safety Performance Function:

```bash
roadsafe build-spf \
  --panel data/processed/segment-year-panel.parquet \
  --contract configs/evaluation-v1.json \
  --output data/processed/spf
```

The command fits an NB2 count model with a log annual vehicle-kilometre offset,
reports validation/test metrics beside the exposure-rate baseline, records
unseen-authority coverage, and writes predictions plus a provenance report. The
SPF remains an evaluated benchmark until it demonstrates reliable improvement
on the declared future and authority holdouts.

The report also includes a joint future-year/authority-held-out backtest with
per-fold membership, failed fits, row coverage and split-level baseline metrics.
See [the September progress report](docs/progress-2026-09.md) for real-panel
results and remaining promotion blockers. Same-year exposure remains a known
feature-timing limitation; these results are not operational forecasts.

Build an exploratory exact-calendar-year lagged feature panel and evaluate the
regularized Poisson challenger:

```bash
roadsafe build-lagged-panel \
  --panel data/processed/contract-v1/segment-year-panel.parquet \
  --contract configs/evaluation-lagged-v1.json \
  --output data/processed/contract-v1/lagged-v1

roadsafe build-spf \
  --panel data/processed/contract-v1/lagged-v1/lagged-feature-panel.parquet \
  --contract configs/evaluation-lagged-v1.json \
  --model ridge-poisson --ridge-alpha 0.01 \
  --output data/processed/contract-v1/lagged-v1/poisson
```

The lagged experiment trains on 2020-2022, preserving 2023 validation and 2024
test years. Rows without exact prior-year history are excluded and reported.
The exposure offset is a historical proxy, not observed prediction-year
traffic. Publication dates are not yet verified, so a one-year lag is not proof
of operational availability. Model outputs remain unpromoted and are not
served by the public map. See the [lagged benchmark report](docs/lagged-benchmark.md).

Build the Empirical Bayes retrospective screening artifact:

```bash
roadsafe build-empirical-bayes \
  --panel data/processed/segment-year-panel.parquet \
  --contract configs/evaluation-v1.json \
  --output data/processed/empirical-bayes
```

This estimates the prior from training years only, then shrinks observed
scoring-period counts toward the exposure-scaled prior mean. The output
includes expected frequency, uncertainty, and positive excess-frequency
signals. It is a retrospective screening layer, not a future prediction or a
causal estimate.

To run the full contract workflow from source templates, use:

```bash
roadsafe build-contract \
  --collision-template 'data/raw/dft-road-casualty-statistics-collision-{year}.csv' \
  --historical-collision-source \
    data/raw/dft-road-casualty-statistics-collision-1979-latest-published-year.csv \
  --road-template 'data/raw/MRDB_{year}_published.shp' \
  --aadf data/raw/dft_traffic_counts_aadf.csv \
  --urban-rural data/processed/urban-rural-2019-2024.csv \
  --contract configs/evaluation-v1.json \
  --output data/processed
```

The command extracts each required reporting year, builds the annual pilot and
network evidence artifacts, and then runs the panel readiness gate. The
explicit historical source is used for 2019 and 2020 because DfT no longer
publishes standalone final collision CSVs for those years. The optional
`--urban-rural` lookup applies the official 2011 two-way classification to each
road count point and records it against each reporting year.

## Documentation

- [Product definition](docs/product.md)
- [Architecture](docs/architecture.md)
- [Data sources and provenance](docs/data-sources.md)
- [Methodology and experiment gates](docs/methodology.md)
- [Limitations and responsible use](docs/limitations.md)
- [Delivery roadmap](docs/roadmap.md)
- [Architecture decisions](docs/adr/)

## Data attribution

Contains public sector information licensed under the Open Government Licence
v3.0. Source: Department for Transport STATS19 road safety open data.

## Licence

Project source code is released under the [MIT License](LICENSE). Source-data
licences and attribution requirements remain applicable to generated datasets
and artifacts.
