# Using RoadSafe UK

The current application is a local West Yorkshire pilot, not a completed national
forecasting product. Start both the API and frontend using [the demo runbook](demo.md).
The usual frontend URL is `http://localhost:5173`; the API uses port 8000.

## Investigation workflow

1. Open **Observed** to view reported collisions. Use All/Fatal/Serious/Slight,
   search by collision ID, and click a collision point for its details.
2. Open **Exposure** to view traffic flow on major-road links. Search by road or
   segment, then choose a **Road segment** from the evidence-panel dropdown.
   The panel distinguishes counted from estimated exposure.
3. Open **Screening** to inspect the observed collision rate for the selected
   link. The denominator is 100 million vehicle-kilometres. This is descriptive
   evidence, not a causal risk estimate.
4. If available, **Retrospective** shows the existing Empirical Bayes screening
   evidence. It is not a forecast. Its current uncertainty field is a proxy with
   an unresolved analytical correction; do not treat it as a validated interval.
5. Select a road segment and use **Export evidence** to download its JSON record,
   source fingerprints and limitations. The X button clears the selection.

## Focus on a road

After choosing a road from the dropdown or map, its outline is highlighted and
other links fade. The focus stays selected across Observed, Exposure, Screening
and Retrospective. Use **Clear selection** beside Export evidence to restore
the network overview.

**Matched collision locations** shows only accepted, unambiguous spatial matches
for that road, using the same distance/ambiguity rules as the network pipeline.
Use its severity controls, click a map point, or select a collision from the
keyboard-accessible list. **Close collision details** closes the point's details
without clearing the road. Search in Observed filters collision IDs within the
current road focus; other modes search roads or segments.

An available `0 of 0 matched collisions` is a verified empty selection. Unavailable
locations or a failed request are not evidence that no collisions occurred.
Point display requires matching road/year and source fingerprints; changing roads
cannot leave the previous road's points behind. These are spatial matches, not
lane-level or causal attributions.

After updating the app, restart its API and reload the browser together. An old
backend without snapshot identity headers is deliberately not combined with the
new client as though its source versions were verified.

Choose the same count point across modes; reselect it if the mode changes or the
search excludes it. Pan and zoom the map to inspect geometry. DfT geometry is
generalised and does not establish lane-level accuracy.

## Disabled controls

| Control | Why it is disabled |
| --- | --- |
| Emerging risk, Compare models, Investigations, Methods in the left rail | Planned views; not implemented yet |
| Agreement | Planned model-agreement view; not implemented yet |
| Retrospective | Disabled when the API does not report retrospective evidence available |
| Export evidence | Requires a selected road segment and loaded source metadata |
| Clear selection | Requires a selected road segment |

The active Network icon denotes the current screen; it is not a separate workflow.
Disabled planned views are not unlocked by clicking harder or changing filters.

If the map data or Retrospective mode are unavailable, check that the API is
running and that the chosen bundle includes retrospective data. Restart the API
after replacing artifacts, then reload the page. The frontend loads availability
at startup; starting the API alone does not refresh an already-open page.

## Current review caveats

The 27 October review identified additional release corrections. The first
ingestion correction is implemented and locally tested; the complete correction
plan is not finished. In particular, filter/selection recovery, independent
observed/network error states, bundle consistency and uncertainty semantics remain
open. A green ingestion test run does not certify the whole analytical release.
