import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { ChatPanel } from "./chat-panel";

const filters = { product_id: "DEMO_VIIRS", province_codes: ["ID-RI"], date_from: "2023-01-01", date_to: "2023-12-31", group_by: "month" as const };

beforeAll(() => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(Response.json({ mode: "mock", apiBaseUrl: null })));
});

describe("ChatPanel", () => {
  it("renders source citations and fixture limitations", async () => {
    const user = userEvent.setup();
    render(<ChatPanel filters={filters} provinceName="Riau" />);
    await user.type(screen.getByLabelText("Ask about wildfire hotspot data"), "What does FRP mean?");
    await user.click(screen.getByRole("button", { name: "Send message" }));
    expect(await screen.findByText("NASA FIRMS — About Active Fire Data", {}, { timeout: 2000 })).toBeInTheDocument();
    expect(screen.getByText(/This demo response is a fixture, not a live retrieval result/)).toBeInTheDocument();
  });
});
