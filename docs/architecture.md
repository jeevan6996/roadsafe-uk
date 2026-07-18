# Architecture

RoadSafe UK separates annual batch computation from read-only application
serving.

```mermaid
flowchart LR
    DFT[DfT STATS19] --> RAW[Versioned raw assets]
    TRAFFIC[DfT traffic counts] --> RAW
    OS[OS Open Roads] --> RAW
    RAW --> VALIDATE[Validation and decoding]
    VALIDATE --> MATCH[Road and exposure matching]
    MATCH --> FEATURES[Segment-period features]
    FEATURES --> MODELS[Statistical and ML evaluation]
    MODELS --> PUBLISH[DuckDB snapshot and PMTiles]
    PUBLISH --> API[FastAPI evidence API]
    PUBLISH --> WEB[React and MapLibre]
```

The browser receives national vector geometry from static PMTiles. FastAPI
serves segment profiles, comparisons, metadata, investigation state, and
reports. Models are scored in batch; map interaction does not invoke training
or online inference.

The exposure pipeline uses British National Grid (`EPSG:27700`) for metric
matching and WGS84 (`EPSG:4326`) for API geometry. Collision-to-link matches,
segment evidence, GeoJSON serving artifacts, and a network quality report are
written separately so rejected matches remain auditable.
