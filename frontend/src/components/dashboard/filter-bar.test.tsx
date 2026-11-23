import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mockMetadata } from "@/lib/api/mock-data";
import { availableCoverageYears, FilterBar, rangeForCoverageYear } from "./filter-bar";

const filters = { product_id: "DEMO_VIIRS", province_codes: ["ID-RI"], date_from: "2023-01-01", date_to: "2023-12-31", group_by: "month" as const };

describe("FilterBar", () => {
  it("renders options supplied by metadata and applies the selection", async () => {
    const onChange = vi.fn();
    const onApply = vi.fn();
    const user = userEvent.setup();
    render(<FilterBar metadata={mockMetadata} filters={filters} onChange={onChange} onApply={onApply} loading={false} />);
    expect(screen.getByRole("option", { name: "Central Kalimantan" })).toBeInTheDocument();
    await user.selectOptions(screen.getByLabelText("Province"), "ID-KT");
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ province_codes: ["ID-KT"] }));
    await user.click(screen.getByRole("button", { name: "Apply filters" }));
    expect(onApply).toHaveBeenCalledOnce();
  });

  it("derives archive years from metadata and applies a complete selected year", async () => {
    const onChange = vi.fn();
    const user = userEvent.setup();
    const metadata = { ...mockMetadata, coverage: { date_min: "2023-01-01", date_max: "2025-12-31", known_unavailable_dates: ["2023-07-26", "2023-07-27"] } };
    render(<FilterBar metadata={metadata} filters={{ ...filters, date_from: "2025-01-01", date_to: "2025-12-31" }} onChange={onChange} onApply={vi.fn()} loading={false} />);

    expect(availableCoverageYears(metadata.coverage)).toEqual([2023, 2024, 2025]);
    await user.selectOptions(screen.getByLabelText("Year"), "2024");
    expect(onChange).toHaveBeenCalledWith(expect.objectContaining({ date_from: "2024-01-01", date_to: "2024-12-31" }));
  });

  it("clamps a year range to partial metadata coverage", () => {
    expect(rangeForCoverageYear({ date_min: "2025-06-01", date_max: "2025-10-31", known_unavailable_dates: [] }, 2025)).toEqual({
      date_from: "2025-06-01",
      date_to: "2025-10-31",
    });
  });
});
