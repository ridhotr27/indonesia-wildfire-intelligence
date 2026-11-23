import { afterEach, describe, expect, it } from "vitest";
import { publicApiUrl } from "@/lib/api/runtime-config";
import { GET } from "./route";

const originalMode = process.env.WILDFIRE_FRONTEND_API_MODE;
const originalUrl = process.env.WILDFIRE_PUBLIC_API_BASE_URL;

afterEach(() => {
  if (originalMode === undefined) delete process.env.WILDFIRE_FRONTEND_API_MODE;
  else process.env.WILDFIRE_FRONTEND_API_MODE = originalMode;
  if (originalUrl === undefined) delete process.env.WILDFIRE_PUBLIC_API_BASE_URL;
  else process.env.WILDFIRE_PUBLIC_API_BASE_URL = originalUrl;
});

describe("runtime API configuration", () => {
  it("defaults to real mode and reads the public URL at request time", async () => {
    delete process.env.WILDFIRE_FRONTEND_API_MODE;
    process.env.WILDFIRE_PUBLIC_API_BASE_URL = "https://api.example.test/api/v1/";
    expect(await GET().json()).toEqual({ mode: "real", apiBaseUrl: "https://api.example.test/api/v1" });
  });

  it("enables synthetic data only through explicit mock mode", async () => {
    process.env.WILDFIRE_FRONTEND_API_MODE = "mock";
    expect(await GET().json()).toEqual({ mode: "mock", apiBaseUrl: null });
  });

  it("rejects credentials and unsafe URL schemes", () => {
    expect(publicApiUrl("https://user:secret@api.example.test/api/v1")).toBeNull();
    expect(publicApiUrl("javascript:alert(1)")).toBeNull();
  });
});
