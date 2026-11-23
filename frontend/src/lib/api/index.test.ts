import { afterEach, describe, expect, it, vi } from "vitest";
import { mockMetadata } from "./mock-data";

afterEach(() => vi.unstubAllGlobals());

describe("runtime client initialization", () => {
  it("clears a rejected configuration promise so a retry can recover", async () => {
    const verifiedMetadata = { ...mockMetadata, data_status: "verified", source: { ...mockMetadata.source, data_status: "verified", provider: "NASA FIRMS", dataset_version: "VNP14IMG.002" } };
    const fetchMock = vi.fn()
      .mockRejectedValueOnce(new TypeError("temporary config outage"))
      .mockResolvedValueOnce(Response.json({ mode: "real", apiBaseUrl: "https://api.example.test/api/v1" }))
      .mockResolvedValueOnce(Response.json(verifiedMetadata));
    vi.stubGlobal("fetch", fetchMock);
    const { apiClient } = await import("./index");

    await expect(apiClient.getMetadata()).rejects.toMatchObject({ code: "DEPENDENCY_UNAVAILABLE" });
    await expect(apiClient.getMetadata()).resolves.toMatchObject({ data_status: "verified" });
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });
});
