import { describe, expect, it } from "vitest";
import traces from "../../../../docs/fixtures/api_contract_v1.1.0.execution_trace.fixture.json";
import oldContract from "../../../../docs/fixtures/api_contract_v1.0.0.fixture.json";
import { validateChat } from "./validation";

type MutableTraceFixture = {
  execution_trace: {
    steps: Array<{ details: Record<string, unknown> }>;
  };
};

function mutableFixture(value: unknown): MutableTraceFixture {
  return structuredClone(value) as MutableTraceFixture;
}

describe("A02 execution trace contract", () => {
  it("validates analytics, RAG, combined, abstention, and old field-absent responses", () => {
    expect(validateChat(traces.chat_analytics).execution_trace?.route).toBe("analytics");
    expect(validateChat(traces.chat_rag).execution_trace?.route).toBe("rag");
    expect(validateChat(traces.chat_combined).execution_trace?.steps).toHaveLength(6);
    expect(validateChat(traces.chat_abstention).execution_trace?.status).toBe("abstained");
    expect(validateChat(oldContract.chat).execution_trace).toBeUndefined();
    expect(validateChat({ ...oldContract.chat, execution_trace: null }).execution_trace).toBeNull();
  });

  it("rejects extra and discriminator-mismatched trace details", () => {
    const extra = mutableFixture(traces.chat_rag);
    extra.execution_trace.steps[1].details.raw_prompt = "forbidden";
    expect(() => validateChat(extra)).toThrow(/invalid chat/i);

    const mismatch = mutableFixture(traces.chat_rag);
    mismatch.execution_trace.steps[1].details.kind = "analytics_query";
    expect(() => validateChat(mismatch)).toThrow(/invalid chat/i);
  });

  it("rejects excessive steps and retrieved items", () => {
    const steps = mutableFixture(traces.chat_rag);
    steps.execution_trace.steps = Array(9).fill(steps.execution_trace.steps[0]);
    expect(() => validateChat(steps)).toThrow(/invalid chat/i);

    const items = mutableFixture(traces.chat_rag);
    const originalItems = items.execution_trace.steps[1].details.items as unknown[];
    items.execution_trace.steps[1].details.items = Array(6).fill(originalItems[0]);
    items.execution_trace.steps[1].details.returned_count = 6;
    expect(() => validateChat(items)).toThrow(/invalid chat/i);
  });

  it("fails closed when trace metrics or normalized chart-period counts disagree", () => {
    const metric = mutableFixture(traces.chat_analytics) as unknown as {
      metrics: Array<{ name: string; value: number; unit: string }>;
      execution_trace: { steps: Array<{ details: Record<string, unknown> }> };
    };
    metric.metrics[0].value = 999;
    expect(() => validateChat(metric)).toThrow(/invalid chat/i);

    const periods = structuredClone(traces.chat_analytics) as unknown as {
      chart: { type: "line"; title: string; series: unknown[] } | null;
      execution_trace: { steps: Array<{ details: Record<string, unknown> }> };
    };
    periods.chart = { type: "line", title: "Synthetic", series: [] };
    expect(() => validateChat(periods)).toThrow(/invalid chat/i);
  });

  it("rejects internal retrieval URLs", () => {
    const internal = mutableFixture(traces.chat_rag);
    internal.execution_trace.steps[1].details.items = [{ chunk_id: "x", title: "internal", url: "https://localhost/private", rank: 1 }];
    internal.execution_trace.steps[1].details.returned_count = 1;
    expect(() => validateChat(internal)).toThrow(/invalid chat/i);
  });

  it("rejects forged retrieval and generation provider claims", () => {
    const retrieval = mutableFixture(traces.chat_rag);
    retrieval.execution_trace.steps[1].details.provider = "remote-vector-service";
    expect(() => validateChat(retrieval)).toThrow(/invalid chat/i);

    const generation = mutableFixture(traces.chat_rag);
    generation.execution_trace.steps[2].details.provider = "openai";
    expect(() => validateChat(generation)).toThrow(/invalid chat/i);
  });
});
