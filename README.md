# RoadSafe UK

Exposure-aware road safety screening for Great Britain, designed to show where
historical evidence, professional statistical methods, and calibrated machine
learning agree or disagree.

> **Current release:** data-foundation preview. The application displays
> observed 2024 collision evidence from a reproducible West Yorkshire pilot. It does
> not yet publish risk predictions or intervention recommendations.

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
- versioned FastAPI endpoints for metadata, summaries, and collision points
- React and MapLibre investigation surface
- fixture-driven unit and API tests

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
