import { expect, test } from "vitest";
import type { EmpiricalBayesResponse, Metadata, SegmentFeature } from "./App";
import { buildEvidenceExport, mergeRetrospectiveEvidence } from "./evidence";

export const segment: SegmentFeature = {
  type: "Feature",
  geometry: { type: "LineString", coordinates: [[-1.8, 53.8], [-1.7, 53.8]] },
  properties: {
    segment_key: "road-1", segment_id: "2024-road-1", count_point_id: 1,
    road_number: "A1", source_year: 2024, all_motor_vehicles: 1000,
    estimation_method: "Counted", estimation_method_detailed: "Manual count",
    link_length_km: 1, collision_count: 3, ksi_count: 2,
    collision_rate_per_100m_vehicle_km: 10,
  },
};
export const metadata: Metadata = {
  dataset: "STATS19", source: "https://www.gov.uk/", source_year: 2024,
  status: "validated", scope: "West Yorkshire pilot", licence: "OGL v3.0",
  caveat: "Not causal risk", collision_sha256: "a".repeat(64),
  network_sha256: "b".repeat(64), empirical_bayes_sha256: "c".repeat(64),
};
const response = (): EmpiricalBayesResponse => {
  const record = { ...segment.properties,
    year: 2024, prior_expected_ksi: 1, expected_ksi: 1.5,
    expected_ksi_std: 1.3, excess_ksi: 0.5,
    road_number: "WRONG", all_motor_vehicles: 999,
  };
  return { available: true, year: 2024, records: [record] };
};

test("accepts the API's projected retrospective record without road or exposure fields", () => {
  const apiResponse: EmpiricalBayesResponse = {
    available: true,
    year: 2024,
    records: [{
      segment_key: "road-1", year: 2024, ksi_count: 2,
      prior_expected_ksi: 1, expected_ksi: 1.5,
      expected_ksi_std: 1.3, excess_ksi: 0.5,
    }],
  };
  const merged = mergeRetrospectiveEvidence(segment, apiResponse);
  expect(merged.properties.expected_ksi).toBe(1.5);
  expect(merged.properties.road_number).toBe("A1");
  expect(merged.properties.all_motor_vehicles).toBe(1000);
});

test("merges model fields without replacing observed geometry or exposure", () => {
  const merged = mergeRetrospectiveEvidence(segment, response());
  expect(merged.properties.expected_ksi).toBe(1.5);
  expect(merged.properties.road_number).toBe("A1");
  expect(merged.properties.all_motor_vehicles).toBe(1000);
  expect(merged.geometry).toBe(segment.geometry);
  expect(segment.properties.expected_ksi).toBeUndefined();
});

test("rejects unavailable, wrong-year, duplicate and mismatched observed records", () => {
  for (const invalid of [
    { ...response(), available: false },
    { ...response(), year: 2023 },
    { ...response(), records: [] },
    { ...response(), records: [...response().records!, ...response().records!] },
    ...[{ year: 2023 }, { ksi_count: 9 }, { segment_key: "unknown" }].map((change) => ({
      ...response(), records: [{ ...response().records![0], ...change }],
    })),
  ]) expect(mergeRetrospectiveEvidence(segment, invalid)).toBe(segment);
});

test.each([NaN, Infinity, -1])("rejects invalid model value %s", (value) => {
  for (const field of ["expected_ksi", "expected_ksi_std", "excess_ksi"]) {
    const invalid = response();
    invalid.records = [{ ...invalid.records![0], [field]: value }];
    expect(mergeRetrospectiveEvidence(segment, invalid)).toBe(segment);
  }
});

test("exports canonical evidence and source fingerprints without a forecast claim", () => {
  const exported = buildEvidenceExport(mergeRetrospectiveEvidence(segment, response()), metadata);
  expect(exported.segment.geometry).toEqual(segment.geometry);
  expect(exported.observed.matched_ksi_collisions).toBe(2);
  expect(exported.exposure.daily_motor_vehicles).toBe(1000);
  expect(exported.retrospective?.expected_ksi).toBe(1.5);
  expect(exported.provenance).toEqual(metadata);
  expect(exported.limitations).toContain("Experimental forecasting models are not included in this export.");
  expect(buildEvidenceExport(segment, metadata).retrospective).toBeNull();
});
