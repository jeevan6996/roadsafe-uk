# RoadSafe UK

Exposure-aware road safety screening for Great Britain, designed to show where
historical evidence, professional statistical methods, and calibrated machine
learning agree or disagree.

> **Current release:** network and exposure preview. The application displays
> observed 2024 collision evidence and DfT traffic exposure for major-road
> links. It does not publish expected-risk scores or intervention advice.

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
- schema, coordinate, duplicate-key, and severity validation
- reproducible West Yorkshire pilot extraction to Parquet
- machine-readable data quality report
- collision-to-link matching with distance and ambiguity diagnostics
- exact DfT count-point to AADF exposure joins with method quality flags
- segment evidence in Parquet and GeoJSON
- versioned FastAPI endpoints for collision and major-road evidence
- React and MapLibre observed/exposure investigation modes
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
ROADSAFE_NETWORK_PATH=data/processed/segment-evidence-2024.geojson \
  uvicorn roadsafe.api.app:app --reload
```

## Build the pilot dataset

Download the official 2024 collision file from the
[DfT road safety open data page](https://www.gov.uk/government/statistical-data-sets/road-safety-open-data),
then run:

```bash
roadsafe build-pilot \
  --source data/raw/dft-road-casualty-statistics-collision-2024.csv \
  --output data/processed
```

The command writes a pilot Parquet file and quality report. Raw and processed
datasets are intentionally excluded from Git.

## Build network and exposure evidence

Download the official 2024 Major Roads Database and AADF CSV from the
[DfT road traffic downloads](https://roadtraffic.dft.gov.uk/downloads), then
run:

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
