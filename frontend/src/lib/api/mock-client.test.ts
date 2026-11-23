import { describe, expect, it } from "vitest";
import { mockApiClient } from "./mock-client";

describe("mock API contract", () => {
  it("exposes metadata-driven filters and explicit demo provenance", async () => {
    const metadata = await mockApiClient.getMetadata();
    expect(metadata.products.length).toBeGreaterThan(0);
    expect(metadata.provinces.length).toBeGreaterThan(0);
    expect(metadata.source.dataset_version).toContain("DEMO");
    expect(metadata.data_freshness_at).toBeNull();
  });

  it("returns WGS84 GeoJSON points bounded by the requested limit", async () => {
    const result = await mockApiClient.getHotspots({ product_id: "DEMO_VIIRS", province_code: "ID-RI", date_from: "2023-01-01", date_to: "2023-12-31", limit: 2 });
    expect(result.type).toBe("FeatureCollection");
    expect(result.features).toHaveLength(2);
    expect(result.features[0].geometry.coordinates[0]).toBeGreaterThan(90);
    expect(result.metadata.limit).toBe(2);
  });

  it("refuses to present burned hectares as a supported metric", async () => {
    const response = await mockApiClient.chat({ message: "How many hectares burned?", product_id: "DEMO_VIIRS", context: { province_code: "ID-RI", date_from: null, date_to: null } });
    expect(response.mode).toBe("unsupported");
    expect(response.answer).toMatch(/can.t calculate burned hectares/i);
  });
});
