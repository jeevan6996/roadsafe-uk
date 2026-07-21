# Changelog

## Unreleased

- generalize collision and network artifacts to validated source years
- preserve stable count-point keys, authority metadata, road category, and road type
- add contract-aware segment-year panel construction and readiness reporting
- add contract-level annual evidence orchestration for evaluation years
- reject duplicate segment-years, year mismatches, invalid exposure/targets, and incomplete subgroups
- add atomic, cached acquisition of official annual DfT inputs with provenance manifests
- validate collision reporting years and required MRDB/AADF archive members before promotion

## 0.2.0 - 2026-07-18

- add DfT 2024 major-road geometry and AADF source contracts
- add collision-to-segment matching with distance and ambiguity rejection
- add exact count-point exposure joins and estimation-method quality flags
- add segment Parquet, GeoJSON, match diagnostics, checksums, and quality report
- add segment and network-summary API endpoints
- add working observed and traffic-exposure map modes
- add a versioned, future-year and authority-grouped evaluation contract

## 0.1.0 - 2026-07-18

- establish validated STATS19 ingestion and West Yorkshire pilot extraction
- add observed-evidence API, map workspace, documentation, tests, and CI
