.PHONY: setup check test api web data-pilot

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

data-pilot:
	roadsafe build-pilot --source data/raw/dft-road-casualty-statistics-collision-2024.csv --output data/processed
