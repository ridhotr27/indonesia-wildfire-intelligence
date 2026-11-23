import { describe, expect, it } from "vitest";
import { latestCalendarYearRange } from "./dashboard";

describe("latestCalendarYearRange", () => {
  it("keeps a single-year dataset unchanged", () => {
    expect(latestCalendarYearRange({ date_min: "2023-01-01", date_max: "2023-12-31", known_unavailable_dates: [] })).toEqual({
      date_from: "2023-01-01",
      date_to: "2023-12-31",
    });
  });

  it("initializes only the latest year of a multi-year dataset", () => {
    expect(latestCalendarYearRange({ date_min: "2023-01-01", date_max: "2025-12-31", known_unavailable_dates: [] })).toEqual({
      date_from: "2025-01-01",
      date_to: "2025-12-31",
    });
  });

  it("does not move before a partial latest-year boundary", () => {
    expect(latestCalendarYearRange({ date_min: "2025-06-01", date_max: "2025-12-31", known_unavailable_dates: [] })).toEqual({
      date_from: "2025-06-01",
      date_to: "2025-12-31",
    });
  });
});
