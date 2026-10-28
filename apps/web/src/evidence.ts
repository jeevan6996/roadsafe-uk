import type { EmpiricalBayesResponse, Metadata, SegmentFeature } from "./App";

export function mergeRetrospectiveEvidence(feature: SegmentFeature, response: EmpiricalBayesResponse): SegmentFeature {
  if (!response.available || response.year !== feature.properties.source_year) return feature;
  const records = response.records?.filter((record) => record.segment_key === feature.properties.segment_key) ?? [];
  if (records.length !== 1) return feature;
  const record = records[0];
  if (record.year !== feature.properties.source_year || record.ksi_count !== feature.properties.ksi_count ||
      ![record.expected_ksi, record.expected_ksi_std, record.excess_ksi].every((value) => typeof value === "number" && Number.isFinite(value) && value >= 0)) return feature;
  return { ...feature, properties: { ...feature.properties,
    expected_ksi: record.expected_ksi, expected_ksi_std: record.expected_ksi_std,
    prior_expected_ksi: record.prior_expected_ksi, excess_ksi: record.excess_ksi,
  } };
}

export function buildEvidenceExport(feature: SegmentFeature, metadata: Metadata) {
  const p = feature.properties;
  const hasModel = typeof p.expected_ksi === "number";
  return {
    schema_version: "1.0",
    exported_at: new Date().toISOString(),
    segment: { key: p.segment_key, id: p.segment_id, count_point_id: p.count_point_id, road: p.road_number, year: p.source_year, geometry: feature.geometry },
    observed: { matched_collisions: p.collision_count, matched_ksi_collisions: p.ksi_count, collision_rate_per_100_million_vehicle_km: p.collision_rate_per_100m_vehicle_km },
    exposure: { daily_motor_vehicles: p.all_motor_vehicles, link_length_km: p.link_length_km, method: p.estimation_method, method_detail: p.estimation_method_detailed },
    retrospective: hasModel ? { method: "Poisson-gamma Empirical Bayes", expected_ksi: p.expected_ksi, standard_deviation_proxy: p.expected_ksi_std, excess_ksi: p.excess_ksi } : null,
    provenance: metadata,
    limitations: [
      "Matched major-road evidence only; ambiguous and out-of-range collisions are excluded.",
      "Observed rates are descriptive. Low counts and estimated exposure require caution.",
      "Empirical Bayes uses the observed period count; it is not a future forecast or causal estimate.",
      "Experimental forecasting models are not included in this export.",
    ],
  };
}
