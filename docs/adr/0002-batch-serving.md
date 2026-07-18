# ADR 0002: Separate batch scoring from application serving

- Status: Accepted
- Date: 2026-07-18

## Decision

Build annual or release-triggered data and model pipelines that publish
immutable serving snapshots. The public API will not perform model inference
for routine map interactions.

## Rationale

The authoritative sources update periodically rather than continuously. Batch
scoring improves reproducibility, latency, cost, and auditability.
