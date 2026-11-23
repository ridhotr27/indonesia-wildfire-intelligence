import { describe, expect, it } from "vitest";
import { GET } from "./route";

describe("MapLibre worker route", () => {
  it("serves the packaged worker as JavaScript", async () => {
    const response = await GET();

    expect(response.headers.get("content-type")).toBe("text/javascript; charset=utf-8");
    expect(await response.text()).toContain("MapLibre GL JS");
  });
});
