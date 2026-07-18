# ADR 0001: Road segments are the primary analytical unit

- Status: Accepted
- Date: 2026-07-18

## Decision

Use authoritative road segments as the production analytical unit. H3 cells
may support aggregation or rendering but will not replace the road network.

## Rationale

Road segments align results with traffic exposure, road attributes, network
connectivity, and investigation workflows. A uniform grid can merge unrelated
roads or divide one road without preserving network meaning.
