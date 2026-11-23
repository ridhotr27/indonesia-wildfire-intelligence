import { afterEach, describe, expect, it, vi } from "vitest";
import { createHttpApiClient } from "./http-client";
import { ApiError } from "./errors";
import { mockHotspots, mockMetadata, mockSummary } from "./mock-data";

const verifiedSource = { ...mockMetadata.source, provider: "NASA FIRMS", dataset_version: "VNP14IMG.002", data_status: "verified" as const, attribution: "NASA FIRMS" };
const verifiedMetadata = { ...mockMetadata, data_status: "verified" as const, source: verifiedSource };

afterEach(() => vi.unstubAllGlobals());

describe("live HTTP API client", () => {
  it("validates a source-verified three-year comparison and exact request echo", async () => {
    const comparison = {
      request_id: "comparison-1",
      operation_id: "hotspot_year_comparison_v1",
      metric: "satellite_hotspot_detections",
      product_id: "VNP14IMG.002_SNPP_FIRMS_SP",
      province_code: "14",
      years: [2023, 2024, 2025],
      points: [
        { year: 2023, count: 120, is_complete: true, coverage_issues: [] },
        { year: 2024, count: 100, is_complete: false, coverage_issues: [{ date_utc: "2024-01-03", coverage_status: "unknown", evidence_url: null, note: null }] },
        { year: 2025, count: 90, is_complete: false, coverage_issues: [{ date_utc: "2025-11-12", coverage_status: "unknown", evidence_url: null, note: null }] },
      ],
      source: verifiedSource,
      caveat: "Hotspot detections are not confirmed wildfires.",
    };
    const fetchMock = vi.fn().mockResolvedValue(Response.json(comparison));
    vi.stubGlobal("fetch", fetchMock);

    const result = await createHttpApiClient("https://api.example.test/api/v1").getYearComparison({ product_id: comparison.product_id, province_code: "14", years: [2023, 2024, 2025] });

    expect(result.points.map((point) => point.count)).toEqual([120, 100, 90]);
    expect(fetchMock).toHaveBeenCalledWith("https://api.example.test/api/v1/hotspots/year-comparison", expect.objectContaining({ method: "POST" }));
  });

  it("exercises metadata, summary, map and chat without synthetic substitution", async () => {
    const responses = [
      verifiedMetadata,
      { ...mockSummary, product_id: "VNP14IMG.002_SNPP_FIRMS_SP", filters: { province_codes: ["14"], date_from: "2023-09-01", date_to: "2023-09-30" }, total: 687, source: verifiedSource },
      { ...mockHotspots, metadata: { ...mockHotspots.metadata, product_id: "VNP14IMG.002_SNPP_FIRMS_SP", filters: { province_codes: ["14"], date_from: "2023-09-01", date_to: "2023-09-30" }, source: verifiedSource, truncated: true } },
      { request_id: "chat-1", answer: "Grounded response", mode: "rag", filters: null, metrics: null, chart: null, map: null, citations: [{ title: "NASA source", url: "https://www.earthdata.nasa.gov/", chunk_id: "chunk-1" }], limitations: [], usage: { llm_calls: 0 } },
    ];
    const fetchMock = vi.fn().mockImplementation(() => Promise.resolve(Response.json(responses.shift())));
    vi.stubGlobal("fetch", fetchMock);
    const client = createHttpApiClient("https://api.example.test/api/v1/");

    expect((await client.getMetadata()).data_status).toBe("verified");
    expect((await client.getSummary({ product_id: "VNP14IMG.002_SNPP_FIRMS_SP", province_codes: ["14"], date_from: "2023-09-01", date_to: "2023-09-30", group_by: "month" })).total).toBe(687);
    expect((await client.getHotspots({ product_id: "VNP14IMG.002_SNPP_FIRMS_SP", province_code: "14", date_from: "2023-09-01", date_to: "2023-09-30", limit: 500 })).metadata.truncated).toBe(true);
    expect((await client.chat({ message: "What does FRP mean?", product_id: "VNP14IMG.002_SNPP_FIRMS_SP", context: { province_code: "14", date_from: null, date_to: null } })).citations[0].url).toMatch(/^https:\/\//);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("rejects mock metadata in real mode", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(mockMetadata)));
    await expect(createHttpApiClient("https://api.example.test/api/v1").getMetadata()).rejects.toMatchObject({ code: "DEPENDENCY_UNAVAILABLE", status: 503 });
  });

  it("rejects a wrong API contract version with a safe typed error", async () => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ ...verifiedMetadata, api_version: "2.0.0" })));
    await expect(createHttpApiClient("https://api.example.test/api/v1").getMetadata()).rejects.toMatchObject({ code: "DEPENDENCY_UNAVAILABLE", status: 503, message: "The API returned an invalid metadata response." });
  });

  it.each([
    ["summary", { request_id: "broken-summary", total: "687" }],
    ["map", { type: "FeatureCollection", features: [], metadata: { request_id: "broken-map", returned: 2 } }],
    ["chat", { request_id: "broken-chat", answer: 42 }],
  ])("rejects malformed %s success payloads", async (endpoint, payload) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json(payload)));
    const client = createHttpApiClient("https://api.example.test/api/v1");
    const action = endpoint === "summary"
      ? client.getSummary({ product_id: "VNP14IMG.002_SNPP_FIRMS_SP", province_codes: ["14"], date_from: "2023-09-01", date_to: "2023-09-30", group_by: "month" })
      : endpoint === "map"
        ? client.getHotspots({ product_id: "VNP14IMG.002_SNPP_FIRMS_SP", province_code: "14", date_from: "2023-09-01", date_to: "2023-09-30", limit: 500 })
        : client.chat({ message: "What is FRP?", product_id: "VNP14IMG.002_SNPP_FIRMS_SP", context: { province_code: null, date_from: null, date_to: null } });
    await expect(action).rejects.toMatchObject({ code: "DEPENDENCY_UNAVAILABLE", status: 503, message: `The API returned an invalid ${endpoint} response.` });
  });

  it.each([
    [429, "RATE_LIMITED", 60],
    [503, "DEPENDENCY_UNAVAILABLE", undefined],
    [504, "REQUEST_TIMEOUT", undefined],
  ])("preserves typed HTTP %i errors", async (status, code, retryAfterSeconds) => {
    vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ request_id: "request-1", error: { code, message: "Bounded failure", ...(retryAfterSeconds ? { retry_after_seconds: retryAfterSeconds } : {}) } }, { status })));
    const result = createHttpApiClient("https://api.example.test/api/v1").getMetadata();
    await expect(result).rejects.toBeInstanceOf(ApiError);
    await expect(result).rejects.toMatchObject({ code, status, retryAfterSeconds });
  });

  it("keeps complete empty, known-gap and truncated responses distinct", async () => {
    const gap = { date_utc: "2023-07-26", coverage_status: "known_satellite_gap" as const, evidence_url: "https://landweb.modaps.eosdis.nasa.gov/displayissue?id=480", note: "Unavailable" };
    const responses = [
      { ...mockSummary, product_id: "VNP14IMG.002_SNPP_FIRMS_SP", filters: { province_codes: ["14"], date_from: "2023-01-01", date_to: "2023-12-31" }, total: 0, series: [], source: verifiedSource },
      { ...mockSummary, product_id: "VNP14IMG.002_SNPP_FIRMS_SP", filters: { province_codes: ["14"], date_from: "2023-01-01", date_to: "2023-12-31" }, total: null, is_complete: false, coverage_issues: [gap], series: [{ period: "2023-07", count: null, is_complete: false, coverage_issues: [gap] }], source: verifiedSource },
      { ...mockHotspots, features: [], metadata: { ...mockHotspots.metadata, product_id: "VNP14IMG.002_SNPP_FIRMS_SP", filters: { province_codes: ["14"], date_from: "2023-01-01", date_to: "2023-12-31" }, returned: 0, truncated: true, source: verifiedSource } },
    ];
    vi.stubGlobal("fetch", vi.fn().mockImplementation(() => Promise.resolve(Response.json(responses.shift()))));
    const client = createHttpApiClient("https://api.example.test/api/v1");
    const request = { product_id: "VNP14IMG.002_SNPP_FIRMS_SP", province_codes: ["14"], date_from: "2023-01-01", date_to: "2023-12-31", group_by: "month" as const };
    expect((await client.getSummary(request)).total).toBe(0);
    expect(await client.getSummary(request)).toMatchObject({ total: null, is_complete: false });
    expect((await client.getHotspots({ ...request, province_code: "14", limit: 500 })).metadata.truncated).toBe(true);
  });
});
