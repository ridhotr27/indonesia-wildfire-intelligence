import { createHttpApiClient } from "./http-client";
import { mockApiClient } from "./mock-client";
import { ApiError } from "./errors";
import type { ApiClient, ApiMode } from "./types";

export * from "./types";
export { ApiError } from "./errors";

type RuntimeConfig = { mode: ApiMode; apiBaseUrl: string | null };
let configuredClient: Promise<ApiClient> | null = null;

async function resolveClient(): Promise<ApiClient> {
  configuredClient ??= fetch("/api/runtime-config", { cache: "no-store" })
    .then(async (response) => {
      if (!response.ok) throw new ApiError("Frontend runtime configuration is unavailable.", "DEPENDENCY_UNAVAILABLE", 503);
      const candidate: unknown = await response.json();
      if (!candidate || typeof candidate !== "object" || !("mode" in candidate) || !["mock", "real"].includes(String(candidate.mode)) || !("apiBaseUrl" in candidate) || (candidate.apiBaseUrl !== null && typeof candidate.apiBaseUrl !== "string")) {
        throw new ApiError("Frontend runtime configuration is invalid.", "DEPENDENCY_UNAVAILABLE", 503);
      }
      const config = candidate as RuntimeConfig;
      if (config.mode === "mock") return mockApiClient;
      if (!config.apiBaseUrl) throw new ApiError("The live API URL is not configured.", "DEPENDENCY_UNAVAILABLE", 503);
      return createHttpApiClient(config.apiBaseUrl);
    })
    .catch((error: unknown) => {
      configuredClient = null;
      if (error instanceof ApiError) throw error;
      throw new ApiError("Frontend runtime configuration is unavailable.", "DEPENDENCY_UNAVAILABLE", 503);
    });
  return configuredClient;
}

export const apiClient: ApiClient = {
  getMetadata: async () => (await resolveClient()).getMetadata(),
  getSummary: async (request) => (await resolveClient()).getSummary(request),
  getHotspots: async (query) => (await resolveClient()).getHotspots(query),
  getYearComparison: async (request) => (await resolveClient()).getYearComparison(request),
  chat: async (request) => (await resolveClient()).chat(request),
};
