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

- OS Open Roads geometry and network identifiers
- official local-authority boundaries
- segment-level urban/rural classification from an authoritative spatial source

Every downloaded file will receive a manifest containing source URL, retrieval
time, checksum, publication status, reporting period, and licence.

The `fetch-sources` command implements this contract for official inputs needed
for final 2019–2024 STATS19 collision years, annual Major Roads Database
archives, and the shared AADF bulk archive. Transfers use a temporary file and
are promoted only after content validation. A local artifact is reused only
when its URL, size, and SHA-256 still agree with its manifest. The catalogue
deliberately excludes provisional years from the modelling panel.

The current DfT page offers standalone final collision files for 2020–2024.
The 2019 input is therefore acquired from the official 1979–latest collision
file and validated by confirming that 2019 is present. This source is much
larger than the annual files and is not represented as an annual-only asset.

## DfT Major Roads Database

The 2024 Major Roads Database supplies year-aligned major-road link geometry.
Each link carries a `CP_Number` that joins directly to DfT traffic statistics.
The source is published as a zipped shapefile under the Open Government
Licence. It does not represent minor roads.

## DfT Annual Average Daily Flow

AADF is the estimated number of vehicles passing a count point on an average
day. The pipeline preserves `estimation_method` and
`estimation_method_detailed`; counted and estimated values are never presented
as equivalent quality. DfT cautions that individual-link estimates are less
robust than regional or national statistics.

The bulk AADF archive covers 2000 onward and supplies the stable
`count_point_id`, reporting year, region, local-authority ID/name/code, road
category, road type, link length, vehicle flows, and estimation method retained
by the annual evidence pipeline. It does not provide the segment-level
urban/rural field required by the evaluation contract.

## OS Open Roads

OS Open Roads is the planned all-roads link-and-node geometry source. It is
available under the Open Government Licence and updated every six months. It
does not itself solve minor-road traffic exposure, so it is not yet used for
published rates.
