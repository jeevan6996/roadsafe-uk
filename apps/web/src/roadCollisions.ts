import { useEffect, useState } from "react";

export type Collision = {
  collision_id: string;
  longitude: number;
  latitude: number;
  severity: number;
  severity_label: string;
  date: string;
  time: string;
  speed_limit: number;
  vehicles: number;
  casualties: number;
  local_authority_code: string;
};

export type SegmentCollisions = {
  segment_key: string;
  source_year: number;
  available: boolean;
  reason: string | null;
  collisions: Collision[];
  collision_sha256: string;
  network_sha256: string;
  matching: { method: string; max_distance_m: number; ambiguity_margin_m: number };
};

type Result =
  | { key: string; status: "ready"; data: SegmentCollisions }
  | { key: string; status: "loading" | "error" };

export function useRoadCollisions(api: string, key: string | null, year?: number, collisionHash?: string, networkHash?: string) {
  const [result, setResult] = useState<Result | null>(null);
  const [attempt, setAttempt] = useState(0);
  useEffect(() => {
    if (!key) { setResult(null); return; }
    if (!collisionHash || !networkHash) { setResult({ key, status: "error" }); return; }
    const controller = new AbortController();
    setResult({ key, status: "loading" });
    void fetch(`${api}/segments/${encodeURIComponent(key)}/collisions`, { signal: controller.signal })
      .then(async (response) => {
        if (!response.ok) throw new Error(`Request failed: ${response.status}`);
        const data = await response.json() as SegmentCollisions;
        if (data.segment_key !== key || data.source_year !== year ||
            data.collision_sha256 !== collisionHash || data.network_sha256 !== networkHash ||
            typeof data.available !== "boolean" || !Array.isArray(data.collisions)) {
          throw new Error("Mismatched road evidence");
        }
        if (!controller.signal.aborted) setResult({ key, status: "ready", data });
      })
      .catch(() => {
        if (!controller.signal.aborted) setResult({ key, status: "error" });
      });
    return () => controller.abort();
  }, [api, key, year, collisionHash, networkHash, attempt]);

  // Key gating also hides old points on the render before effect cleanup runs.
  const current = key && result?.key === key && (result.status !== "ready" || (
    result.data.source_year === year && result.data.collision_sha256 === collisionHash && result.data.network_sha256 === networkHash
  )) ? result : null;
  return {
    status: current?.status ?? "loading",
    data: current?.status === "ready" ? current.data : null,
    retry: () => { setResult(null); setAttempt((value) => value + 1); },
  };
}
