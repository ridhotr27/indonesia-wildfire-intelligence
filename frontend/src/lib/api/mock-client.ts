import { ApiError } from "./errors";
import { mockChatResponse, mockHotspots, mockMetadata, mockSummary } from "./mock-data";
import type { ApiClient, ChatRequest, HotspotQuery, SummaryRequest } from "./types";

const wait = (milliseconds = 420) => new Promise((resolve) => setTimeout(resolve, milliseconds));

export const mockApiClient: ApiClient = {
  async getMetadata() {
    await wait(160);
    return structuredClone(mockMetadata);
  },
  async getSummary(request: SummaryRequest) {
    await wait();
    if (request.date_from > request.date_to) throw new ApiError("The start date must be before the end date.", "INVALID_FILTER", 400, "demo-error-filter");
    const response = structuredClone(mockSummary);
    response.product_id = request.product_id;
    response.filters = { province_codes: request.province_codes, date_from: request.date_from, date_to: request.date_to };
    return response;
  },
  async getHotspots(query: HotspotQuery) {
    await wait();
    const response = structuredClone(mockHotspots);
    response.features = response.features.filter((feature) => feature.properties.province_code === query.province_code).slice(0, query.limit);
    response.metadata.product_id = query.product_id;
    response.metadata.filters = { province_codes: [query.province_code], date_from: query.date_from, date_to: query.date_to };
    response.metadata.returned = response.features.length;
    response.metadata.limit = query.limit;
    return response;
  },
  async getYearComparison(request) {
    await wait();
    return {
      request_id: "demo-year-comparison",
      operation_id: "hotspot_year_comparison_v1",
      metric: "satellite_hotspot_detections",
      product_id: request.product_id,
      province_code: request.province_code,
      years: request.years,
      points: request.years.map((year, index) => ({ year, count: 100 + index * 25, is_complete: true, coverage_issues: [] })),
      source: structuredClone(mockMetadata.source),
      caveat: "Hotspot detections are not confirmed wildfires.",
    };
  },
  async chat(request: ChatRequest) {
    await wait(720);
    const normalized = request.message.toLowerCase();
    if (normalized.includes("rate limit")) throw new ApiError("Demo quota reached. Try again later.", "RATE_LIMITED", 429, "demo-rate-limit", 60);
    if (normalized.includes("timeout")) throw new ApiError("The bounded request timed out.", "REQUEST_TIMEOUT", 504, "demo-timeout");
    if (normalized.includes("hectare") || normalized.includes("confirmed wildfire")) {
      return {
        ...structuredClone(mockChatResponse),
        request_id: "demo-chat-unsupported",
        mode: "unsupported",
        answer: "I can’t calculate burned hectares or verify confirmed wildfire incidents from hotspot detections. This tool explores satellite-detected thermal anomalies only.",
        citations: [],
        limitations: ["FIRMS hotspot detections do not measure burned area.", "Use an official incident authority for confirmed wildfire information."],
      };
    }
    return structuredClone(mockChatResponse);
  },
};
