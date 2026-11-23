import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { YearComparisonEvidence } from "./year-comparison";

describe("YearComparisonEvidence", () => {
  it("keeps incomplete-year missing dates unknown instead of presenting zero", () => {
    render(<YearComparisonEvidence comparison={{
      request_id: "comparison-1",
      operation_id: "hotspot_year_comparison_v1",
      metric: "satellite_hotspot_detections",
      product_id: "VNP14IMG.002_SNPP_FIRMS_SP",
      province_code: "14",
      years: [2023, 2024, 2025],
      points: [
        { year: 2023, count: 100, is_complete: true, coverage_issues: [] },
        { year: 2024, count: 80, is_complete: false, coverage_issues: [{ date_utc: "2024-01-03", coverage_status: "unknown", evidence_url: null, note: null }] },
        { year: 2025, count: null, is_complete: false, coverage_issues: [{ date_utc: "2025-11-12", coverage_status: "unknown", evidence_url: null, note: null }] },
      ],
      source: { provider: "NASA FIRMS", dataset_version: "VNP14IMG.002", data_status: "verified", url: "https://firms.modaps.eosdis.nasa.gov/", attribution: "NASA FIRMS" },
      caveat: "Hotspot detections are not confirmed wildfires.",
    }} />);

    expect(screen.getByText("Unavailable")).toBeInTheDocument();
    expect(screen.getAllByText(/missing dates unknown, not zero/i)).toHaveLength(2);
  });
});
