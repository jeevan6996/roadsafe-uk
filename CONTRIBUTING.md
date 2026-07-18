# Contributing

RoadSafe UK welcomes reproducible improvements to data quality, statistical
methods, evaluation, accessibility, and the investigation workflow.

## Before opening a change

1. Open or reference an issue that states the decision problem and acceptance
   criteria.
2. Check existing issues and pull requests to avoid duplicate work.
3. For analytical changes, document the prediction time, target, feature
   availability, spatial and temporal split, baseline, and calibration plan.
4. Never commit restricted, personal, raw, or derived bulk data.

## Local checks

```bash
make check
make test
cd apps/web && npm run build && npm audit --audit-level=moderate
```

Data-pipeline changes must include a fixture test and preserve provenance in
the generated quality report. Model changes must beat a declared simple
baseline on held-out future periods and unseen authorities before their output
can appear as an accepted product layer.

## Pull requests

Keep changes focused and explain user impact, evidence, limitations, and test
results. Screenshots are required for visible interface changes. By
contributing, you agree that your code is licensed under this repository's MIT
License.
