import { ApiError, isErrorResponse } from "./errors";
import type { ApiClient, ChatRequest, HotspotFeatureCollection, HotspotQuery, SummaryRequest, YearComparisonRequest } from "./types";
import { validateChat, validateHotspots, validateMetadata, validateSummary, validateYearComparison } from "./validation";
import { validateA03Chat } from "./a03-contract-proposal";

async function request<T>(baseUrl: string, path: string, init?: RequestInit): Promise<T> {
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      ...init,
      headers: { "Content-Type": "application/json", ...init?.headers },
      signal: init?.signal ?? AbortSignal.timeout(120_000),
    });
  } catch (error) {
    if (error instanceof DOMException && ["TimeoutError", "AbortError"].includes(error.name)) throw new ApiError("The request timed out.", "REQUEST_TIMEOUT", 504);
    throw new ApiError("The API is currently unavailable.", "DEPENDENCY_UNAVAILABLE", 503);
  }
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    if (isErrorResponse(payload)) throw new ApiError(payload.error.message, payload.error.code, response.status, payload.request_id, payload.error.retry_after_seconds);
    throw new ApiError("The API returned an unexpected error response.", "HTTP_ERROR", response.status);
  }
  return payload as T;
}

function requireVerified<T extends { source: { data_status: string } }>(payload: T): T {
  if (payload.source.data_status !== "verified") {
    throw new ApiError("Live mode refused a non-verified data response.", "DEPENDENCY_UNAVAILABLE", 503);
  }
  return payload;
}

function requireVerifiedMap(payload: HotspotFeatureCollection): HotspotFeatureCollection {
  if (payload.metadata.source.data_status !== "verified") {
    throw new ApiError("Live mode refused a non-verified map response.", "DEPENDENCY_UNAVAILABLE", 503, payload.metadata.request_id);
  }
  return payload;
}

function sameSummaryRequest(payload: ReturnType<typeof validateSummary>, request: SummaryRequest): boolean {
  return payload.product_id === request.product_id
    && payload.filters.date_from === request.date_from
    && payload.filters.date_to === request.date_to
    && payload.filters.province_codes.length === request.province_codes.length
    && payload.filters.province_codes.every((code, index) => code === request.province_codes[index]);
}

function sameMapQuery(payload: HotspotFeatureCollection, query: HotspotQuery): boolean {
  return payload.metadata.product_id === query.product_id
    && payload.metadata.filters.date_from === query.date_from
    && payload.metadata.filters.date_to === query.date_to
    && payload.metadata.filters.province_codes.length === 1
    && payload.metadata.filters.province_codes[0] === query.province_code
    && payload.metadata.limit <= query.limit;
}

export function createHttpApiClient(baseUrl: string): ApiClient {
  const normalizedBaseUrl = baseUrl.replace(/\/$/, "");
  let metadataPromise: ReturnType<ApiClient["getMetadata"]> | null = null;
  const loadMetadata = async () => {
    metadataPromise ??= request<unknown>(normalizedBaseUrl, "/metadata")
      .then(validateMetadata)
      .catch((error) => { metadataPromise = null; throw error; });
    return metadataPromise;
  };
  return {
  getMetadata: async () => {
    const payload = await loadMetadata();
    if (payload.data_status !== "verified" || payload.source.data_status !== "verified") {
      throw new ApiError("Live mode refused non-verified metadata.", "DEPENDENCY_UNAVAILABLE", 503, payload.request_id);
    }
    return payload;
  },
  getSummary: async (body: SummaryRequest) => {
    const payload = validateSummary(await request<unknown>(normalizedBaseUrl, "/hotspots/summary", { method: "POST", body: JSON.stringify(body) }));
    if (!sameSummaryRequest(payload, body)) throw new ApiError("The API returned an invalid summary response.", "DEPENDENCY_UNAVAILABLE", 503, payload.request_id);
    return requireVerified(payload);
  },
  getHotspots: async (query: HotspotQuery) => {
    const params = new URLSearchParams({ ...query, limit: String(query.limit) });
    const payload = validateHotspots(await request<unknown>(normalizedBaseUrl, `/hotspots/geojson?${params.toString()}`));
    if (!sameMapQuery(payload, query)) throw new ApiError("The API returned an invalid map response.", "DEPENDENCY_UNAVAILABLE", 503, payload.metadata.request_id);
    return requireVerifiedMap(payload);
  },
  getYearComparison: async (body: YearComparisonRequest) => {
    const payload = validateYearComparison(await request<unknown>(normalizedBaseUrl, "/hotspots/year-comparison", { method: "POST", body: JSON.stringify(body) }));
    if (payload.product_id !== body.product_id || payload.province_code !== body.province_code || JSON.stringify(payload.years) !== JSON.stringify(body.years)) {
      throw new ApiError("The API returned an invalid year comparison response.", "DEPENDENCY_UNAVAILABLE", 503, payload.request_id);
    }
    return requireVerified(payload);
  },
  chat: async (body: ChatRequest) => {
    const value = await request<unknown>(normalizedBaseUrl, "/chat", { method: "POST", body: JSON.stringify(body) });
    if (value && typeof value === "object" && "province_analytics" in value && value.province_analytics) {
      return validateA03Chat(value, await loadMetadata());
    }
    return validateChat(value);
  },
  };
}
