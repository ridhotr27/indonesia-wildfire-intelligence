import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import traces from "../../../../docs/fixtures/api_contract_v1.1.0.execution_trace.fixture.json";
import backendFixture from "../../../../backend/tests/fixtures/i03_execution_trace_backend.fixture.json";
import { validateChat } from "@/lib/api/validation";
import { ExecutionTraceDisclosure } from "./execution-trace";

const verifiedData = {
  dataStatus: "verified" as const,
  source: {
    provider: "NASA FIRMS",
    dataset_version: "VNP14IMG.002",
    data_status: "verified" as const,
    url: "https://firms.modaps.eosdis.nasa.gov/",
    attribution: "NASA FIRMS",
  },
};

const mockData = {
  dataStatus: "mock" as const,
  source: {
    provider: "Synthetic fixture",
    dataset_version: "DEMO-NOT-OBSERVATIONS",
    data_status: "mock" as const,
    url: "https://firms.modaps.eosdis.nasa.gov/",
    attribution: "Synthetic fixture",
  },
};

const cases = [
  ["analytics", traces.chat_analytics, "Monthly hotspot count"],
  ["rag", traces.chat_rag, "nasa-firms-docs"],
  ["combined", traces.chat_combined, "Local ollama"],
  ["unsupported", traces.chat_abstention, "No operation ran: missing province."],
] as const;

describe("I03 ExecutionTraceDisclosure", () => {
  it.each(cases)("renders a collapsed, keyboard-operable %s trace", async (_route, fixture, expected) => {
    const user = userEvent.setup();
    const response = validateChat(fixture);
    render(<ExecutionTraceDisclosure trace={response.execution_trace} />);
    const disclosure = screen.getByText("How this answer was generated").closest("details");
    expect(disclosure).not.toHaveAttribute("open");
    expect(screen.queryByText(expected)).not.toBeVisible();
    await user.tab();
    expect(screen.getByText("How this answer was generated").closest("summary")).toHaveFocus();
    await user.click(screen.getByText("How this answer was generated"));
    expect(disclosure).toHaveAttribute("open");
    expect(screen.getByText(expected)).toBeVisible();
  });

  it("uses the backend-supported order and secures retrieved links", async () => {
    const user = userEvent.setup();
    const response = validateChat(traces.chat_rag);
    const actualOrder = response.execution_trace?.steps.map((step) => step.kind) ?? [];
    expect(actualOrder.filter((kind) => backendFixture.supported_step_order.rag.includes(kind as "route_selection"))).toEqual(backendFixture.supported_step_order.rag);
    render(<ExecutionTraceDisclosure trace={response.execution_trace} />);
    await user.click(screen.getByText("How this answer was generated"));
    expect(screen.getByRole("link", { name: /NASA FIRMS FAQ/ })).toHaveAttribute("href", "https://firms.modaps.eosdis.nasa.gov/faq/");
    expect(screen.getByRole("link", { name: /NASA FIRMS FAQ/ })).toHaveAttribute("rel", "noopener noreferrer");
  });

  it("renders nothing for absent or null v1.0-compatible traces", () => {
    const { container, rerender } = render(<ExecutionTraceDisclosure trace={undefined} />);
    expect(container).toBeEmptyDOMElement();
    rerender(<ExecutionTraceDisclosure trace={null} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("rejects unsafe URLs, extra debug fields, and raw prompt-like content before rendering", () => {
    const unsafe = structuredClone(traces.chat_rag) as unknown as { execution_trace: { steps: Array<{ details: Record<string, unknown> }> } };
    unsafe.execution_trace.steps[1].details.items = [{ chunk_id: "x", title: "unsafe", url: "javascript:alert(1)", rank: 1 }];
    unsafe.execution_trace.steps[1].details.returned_count = 1;
    unsafe.execution_trace.steps[1].details.raw_prompt = "secret prompt";
    expect(() => validateChat(unsafe)).toThrow(/invalid chat/i);
  });

  it("explains the verified fixed ClickHouse path and exact analytics metric", async () => {
    const user = userEvent.setup();
    const response = validateChat(traces.chat_analytics);
    render(<ExecutionTraceDisclosure trace={response.execution_trace} response={response} dataContext={verifiedData} />);
    await user.click(screen.getByText("How this answer was generated"));

    expect(screen.getByRole("heading", { name: "How the data became this answer" })).toBeVisible();
    expect(screen.getAllByText('hotspot_summary_v1(province_codes=["13"], date_from="2023-09-01", date_to="2023-09-30")')).toHaveLength(2);
    expect(screen.getByText(/server-owned, parameterized, read-only ClickHouse reads for monthly counts and coverage/)).toBeVisible();
    expect(screen.getByText(/No SQL came from you or the LLM/)).toBeVisible();
    expect(screen.getByText(/exact result was 414 detections/)).toBeVisible();
    expect(screen.getByText(/No LLM generated or changed this number/)).toBeVisible();
    expect(screen.getByText(/NASA FIRMS · VNP14IMG\.002/)).toBeVisible();
    expect(screen.getByText("Monthly periods in result")).toBeVisible();
  });

  it("labels synthetic analytics without naming or implying ClickHouse", async () => {
    const user = userEvent.setup();
    const response = validateChat(traces.chat_analytics);
    render(<ExecutionTraceDisclosure trace={response.execution_trace} response={response} dataContext={mockData} />);
    await user.click(screen.getByText("How this answer was generated"));

    expect(screen.getByText(/synthetic repository for interface testing/)).toBeVisible();
    expect(screen.getByText(/No production analytics database ran/)).toBeVisible();
    expect(screen.queryByText(/ClickHouse/i)).not.toBeInTheDocument();
  });

  it("keeps the deterministic metric separate from the documentation model in combined mode", async () => {
    const user = userEvent.setup();
    const response = validateChat(traces.chat_combined);
    render(<ExecutionTraceDisclosure trace={response.execution_trace} response={response} dataContext={verifiedData} />);
    await user.click(screen.getByText("How this answer was generated"));

    expect(screen.getByText(/deterministic analytics metric was kept separate from the local documentation path/)).toBeVisible();
    expect(screen.getByText(/could not create, replace, or modify this metric/)).toBeVisible();
    expect(screen.getByText("Local documentation answer generated")).toBeVisible();
  });

  it.each([traces.chat_rag, traces.chat_abstention])("does not invent an analytics flow for non-analytics traces", async (fixture) => {
    const user = userEvent.setup();
    const response = validateChat(fixture);
    render(<ExecutionTraceDisclosure trace={response.execution_trace} response={response} dataContext={verifiedData} />);
    await user.click(screen.getByText("How this answer was generated"));

    expect(screen.queryByRole("heading", { name: "How the data became this answer" })).not.toBeInTheDocument();
    expect(screen.queryByText(/ClickHouse/i)).not.toBeInTheDocument();
  });

  it("omits provider-specific lineage when metadata is absent or inconsistent", async () => {
    const user = userEvent.setup();
    const response = validateChat(traces.chat_analytics);
    const { rerender } = render(<ExecutionTraceDisclosure trace={response.execution_trace} response={response} />);
    await user.click(screen.getByText("How this answer was generated"));
    expect(screen.queryByRole("heading", { name: "How the data became this answer" })).not.toBeInTheDocument();

    rerender(<ExecutionTraceDisclosure trace={response.execution_trace} response={response} dataContext={{ ...verifiedData, dataStatus: "mock" }} />);
    expect(screen.queryByRole("heading", { name: "How the data became this answer" })).not.toBeInTheDocument();
  });

  it("reports only structured coverage dates and distinguishes unavailable coverage", async () => {
    const user = userEvent.setup();
    const fixture = structuredClone(traces.chat_analytics) as unknown as Record<string, unknown> & {
      chart: unknown;
    };
    fixture.chart = {
      type: "line",
      title: "Synthetic coverage example",
      series: [{
        period: "2023-07",
        count: 414,
        is_complete: false,
        coverage_issues: [{ date_utc: "2023-07-26", coverage_status: "known_satellite_gap", evidence_url: "https://landweb.modaps.eosdis.nasa.gov/displayissue?id=480", note: "Synthetic coverage example" }],
      }],
    };
    const response = validateChat(fixture);
    render(<ExecutionTraceDisclosure trace={response.execution_trace} response={response} dataContext={verifiedData} />);
    await user.click(screen.getByText("How this answer was generated"));
    expect(screen.getByText(/observed subtotal was retained for available periods, and 2023-07-26 was marked as unavailable or unknown coverage/)).toBeVisible();
  });

  it("never renders response-controlled SQL, paths, credentials, or HTML as an execution label", async () => {
    const user = userEvent.setup();
    const fixture = structuredClone(traces.chat_analytics);
    fixture.execution_trace.steps[0].label = '<script>SELECT password FROM /Users/private</script>';
    const response = validateChat(fixture);
    const { container } = render(<ExecutionTraceDisclosure trace={response.execution_trace} response={response} dataContext={verifiedData} />);
    await user.click(screen.getByText("How this answer was generated"));
    expect(screen.queryByText(/SELECT password FROM/)).not.toBeInTheDocument();
    expect(container.querySelector("script")).toBeNull();
    expect(screen.getByText("Request route selected")).toBeVisible();
  });
});
