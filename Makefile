.PHONY: setup check test api web data-fetch data-pilot data-network data-contract

setup:
	python -m pip install -e '.[dev]'
	cd apps/web && npm install

check:
	ruff check .
	ruff format --check .
	mypy src
	cd apps/web && npm run check

test:
	pytest
	cd apps/web && npm test -- --run

api:
	uvicorn roadsafe.api.app:app --reload

web:
	cd apps/web && npm run dev

data-fetch:
	roadsafe fetch-sources --years 2019 2020 2021 2022 2023 2024 --output data/raw

data-pilot:
	roadsafe build-pilot --source data/raw/dft-road-casualty-statistics-collision-2024.csv --output data/processed

data-network:
	roadsafe build-network --collisions data/processed/pilot-collisions-2024.parquet --roads data/raw/MRDB_2024_published.shp --aadf data/raw/dft_traffic_counts_aadf.csv --output data/processed --year 2024

data-contract:
	roadsafe build-contract --collision-template 'data/raw/dft-road-casualty-statistics-collision-{year}.csv' --historical-collision-source data/raw/dft-road-casualty-statistics-collision-1979-latest-published-year.csv --road-template 'data/raw/MRDB_{year}_published.shp' --aadf data/raw/dft_traffic_counts_aadf.csv --contract configs/evaluation-v1.json --output data/processed
