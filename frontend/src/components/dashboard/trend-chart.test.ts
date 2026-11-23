import { describe, expect, it } from "vitest";
import { trendPeriodLabel } from "./trend-chart";

describe("trendPeriodLabel", () => {
  it("keeps the year visible for multi-year analytics", () => {
    expect(trendPeriodLabel("2024-03", true)).toBe("2024-03");
  });

  it("uses a compact month label within one year", () => {
    expect(trendPeriodLabel("2025-11", false)).toBe("11");
  });
});
