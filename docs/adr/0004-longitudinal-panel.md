# ADR 0004: Gate modelling on a longitudinal count-point panel

## Status

Accepted for the statistical-screening foundation.

## Decision

Use the DfT count-point identifier as the stable analytical key across annual
major-road evidence, while retaining the year-specific segment identifier and
geometry source year. Assemble annual artifacts into a segment-year Parquet
panel before model fitting and assess it against the versioned evaluation
contract.

The readiness gate requires every declared temporal partition, unique
segment-year rows, valid exposure and targets, and complete fields for each
required subgroup. Grouped geographic holdout additionally requires at least
two local-authority groups. The gate emits a blocked report instead of fitting
or publishing a model when any requirement is unmet.

## Consequences

Count points can be compared longitudinally without pretending annual geometry
is immutable. Input and contract checksums preserve provenance. The current
2024 pilot remains unsuitable for statistical screening until earlier annual
evidence and authoritative segment-level urban/rural classification are added.
An unbalanced panel may still be retained for future modelling, but completeness
is measured and must be addressed explicitly in each experiment.
