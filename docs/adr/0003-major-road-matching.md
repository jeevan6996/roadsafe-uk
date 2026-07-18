# ADR 0003: Match collisions to year-aligned DfT major-road links

## Status

Accepted for the exposure pilot.

## Decision

Use the DfT Major Roads Database for the 2024 exposure slice. Accept a
collision-to-link match only when the nearest link is within 50 metres and the
next candidate is more than 10 metres farther away. Join AADF exactly through
the Major Roads Database `CP_Number` and AADF `count_point_id`.

## Consequences

The first exposure layer covers major roads only. Unmatched and ambiguous
collisions remain in diagnostics but never enter segment rates. OS Open Roads
remains the planned all-roads geometry source, but minor-road exposure needs a
separate defensible method before publication.
