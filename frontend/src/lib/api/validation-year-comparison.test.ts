import { describe, expect, it } from "vitest";
import { validateChat } from "./validation";

const source = { provider: "NASA FIRMS", dataset_version: "VNP14IMG.002", data_status: "verified", url: "https://firms.modaps.eosdis.nasa.gov/", attribution: "NASA FIRMS" } as const;
const issue = { date_utc: "2025-11-12", coverage_status: "unknown", evidence_url: null, note: null } as const;

describe("D08 year comparison chat validation", () => {
  it("accepts the fixed read-only YoY operation and preserves unknown coverage", () => {
    const comparison = {
      request_id: "comparison-1", operation_id: "hotspot_year_comparison_v1", metric: "satellite_hotspot_detections",
      product_id: "VNP14IMG.002_SNPP_FIRMS_SP", province_code: "14", years: [2023, 2024, 2025],
      points: [
        { year: 2023, count: 120, is_complete: true, coverage_issues: [] },
        { year: 2024, count: 100, is_complete: true, coverage_issues: [] },
        { year: 2025, count: 90, is_complete: false, coverage_issues: [issue] },
      ], source, caveat: "Hotspot detections are not confirmed wildfires.",
    };
    const response = validateChat({
      request_id: "chat-1", answer: "Year-over-year hotspot detections.", mode: "analytics",
      filters: { province_codes: ["14"], date_from: "2023-01-01", date_to: "2025-12-31" },
      metrics: comparison.points.map((point) => ({ name: `satellite_hotspot_detections_${point.year}`, value: point.count, unit: "detections" })),
      chart: null, map: null, citations: [], limitations: ["Missing dates remain unknown, not zero."], usage: { llm_calls: 0 }, year_comparison: comparison,
      execution_trace: { trace_version: "1.0", route: "analytics", status: "complete", steps: [
        { sequence: 1, kind: "route_selection", status: "complete", label: "Route", details: { kind: "route_selection", route: "analytics" } },
        { sequence: 2, kind: "filter_resolution", status: "complete", label: "Filters", details: { kind: "filter_resolution", province_codes: ["14"], date_from: "2023-01-01", date_to: "2025-12-31", province_source: "message", date_from_source: "message", date_to_source: "message", reason_codes: [], outcome: "resolved" } },
        { sequence: 3, kind: "analytics_query", status: "complete", label: "YoY", details: { kind: "analytics_query", operation_id: "hotspot_year_comparison_v1", parameters: { province_code: "14", years: [2023, 2024, 2025] }, read_only: true, returned_rows: 3, metric_name: "satellite_hotspot_detections", metric_value: null } },
      ] },
    });

    expect(response.year_comparison?.points[2]).toMatchObject({ count: 90, is_complete: false, coverage_issues: [issue] });
  });
});
