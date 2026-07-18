# Limitations and responsible use

- STATS19 excludes unreported collisions, near misses, and non-injury incidents.
- Reported severity and collection practices have changed over time.
- Collision concentration is not equivalent to exposure-normalized risk.
- Traffic estimates have different quality and coverage across road classes.
- Model association does not establish that a road feature caused an outcome.
- Sparse locations require explicit uncertainty and may not support ranking.
- The application is not an emergency, routing, insurance, enforcement, or
  autonomous-driving system.

RoadSafe UK will recommend questions for investigation, not physical
interventions. Any future intervention evidence must come from separately
reviewed causal or safety-effectiveness research.

## Major-road exposure scope

The current exposure layer covers DfT major-road links only. It must not be used
to compare major roads with minor roads, because minor-road collisions have no
equivalent link exposure in this release. AADF values may be counted or
estimated; their method is retained in every segment record and interface.

Spatial matching also introduces uncertainty near junctions and parallel
carriageways. Matches outside 50 metres or with near-equal candidates are
excluded rather than assigned automatically.
