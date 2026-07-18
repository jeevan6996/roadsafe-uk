# Data sources and provenance

## DfT STATS19

The primary source contains police-reported personal-injury collisions on
public roads in Great Britain. Collision, vehicle, and casualty tables are
published separately. Final annual and provisional data must remain visibly
distinct.

The committed fixture contains the first 12 source-order 2024 records within
the documented West Yorkshire pilot bounding box. It exists only for tests and
local UI development. It retains source identifiers and is not synthetic.

Source: <https://www.gov.uk/government/statistical-data-sets/road-safety-open-data>

Licence: Open Government Licence v3.0.

## Planned enrichment

- DfT annual average daily flow and count-point quality metadata
- OS Open Roads geometry and network identifiers
- official local-authority boundaries

Every downloaded file will receive a manifest containing source URL, retrieval
time, checksum, publication status, reporting period, and licence.
