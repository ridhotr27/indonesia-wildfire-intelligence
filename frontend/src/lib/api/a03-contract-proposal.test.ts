import { describe, expect, it } from "vitest";
import fixture from "../../../../docs/fixtures/api_contract_v1.2.0.province_analytics.fixture.json";
import edgeFixture from "../../../../docs/fixtures/api_contract_v1.2.0.province_analytics.edge.fixture.json";
import oldContract from "../../../../docs/fixtures/api_contract_v1.0.0.fixture.json";
import oldTrace from "../../../../docs/fixtures/api_contract_v1.1.0.execution_trace.fixture.json";
import { validateA03Chat } from "./a03-contract-proposal";

// Proposal mutation tests intentionally traverse arbitrary JSON fixture paths.
// eslint-disable-next-line @typescript-eslint/no-explicit-any
type Mutable = Record<string, any>;
const mutable = (value: unknown): Mutable => structuredClone(value) as Mutable;

function metadataFor(value: Mutable) {
  const result = value.province_analytics.result;
  const provinces = Array.from({ length: 38 }, (_, index) => ({ province_code: String(index + 1).padStart(2, "0"), display_name: `Synthetic placeholder ${index + 1}` }));
  for (const row of result.rows) provinces[row.province_order - 1] = { province_code: row.province_code, display_name: row.province_name };
  return { data_status: result.source.data_status as "mock" | "verified", source: result.source, products: [{ product_id: result.product_id, display_name: "Synthetic product" }], provinces };
}

function chatForRankingResult(resultValue: unknown): Mutable {
  const value = mutable(fixture.chat_highest_top_1);
  const result = mutable(resultValue);
  value.province_analytics.result = result;
  value.filters.date_from = result.date_from;
  value.filters.date_to = result.date_to;
  value.metrics[0].value = result.rows[0]?.count ?? null;
  value.province_analytics.execution.parameters.date_from = result.date_from;
  value.province_analytics.execution.parameters.date_to = result.date_to;
  value.province_analytics.execution.parameters.direction = result.direction;
  value.province_analytics.execution.parameters.selection = result.selection;
  value.province_analytics.execution.returned_rows = result.rows.length;
  value.province_analytics.execution.metric_value = result.rows[0]?.count ?? null;
  return value;
}

function unavailableComparisonChat(): Mutable {
  const value = mutable(fixture.chat_two_province_complete);
  const result = mutable(edgeFixture.unavailable_breakdown_result);
  value.province_analytics.result = result;
  value.filters.date_from = result.date_from;
  value.filters.date_to = result.date_to;
  value.metrics[0].value = null;
  value.province_analytics.execution.parameters.date_from = result.date_from;
  value.province_analytics.execution.parameters.date_to = result.date_to;
  value.province_analytics.execution.parameters.comparison_requested = true;
  value.province_analytics.execution.metric_value = null;
  return value;
}

function deleteNested(value: Mutable, path: Array<string | number>) {
  let current: Mutable = value;
  for (const segment of path.slice(0, -1)) current = current[segment] as Mutable;
  delete current[path.at(-1) as string | number];
}

describe("A03 province analytics proposal", () => {
  it("validates all proposal fixtures and preserves old responses", () => {
    const cases = Object.entries(fixture).filter(([name]) => name.startsWith("chat_"));
    expect(cases.length).toBeGreaterThanOrEqual(9);
    for (const [, value] of cases) expect(validateA03Chat(value, metadataFor(mutable(value))).province_analytics).toBeDefined();
    expect(validateA03Chat(oldContract.chat).province_analytics).toBeUndefined();
    expect(validateA03Chat(oldTrace.chat_analytics).province_analytics).toBeUndefined();
  });

  it("checks canonical code, name, order, and source against metadata", () => {
    const value = mutable(fixture.chat_two_province_complete);
    const source = value.province_analytics.result.source;
    const metadata = {
      data_status: "mock" as const,
      source,
      products: [{ product_id: "DEMO_VIIRS", display_name: "Synthetic product" }],
      provinces: Array.from({ length: 38 }, (_, index) => ({
        province_code: String(index + 1).padStart(2, "0"),
        display_name: `Synthetic Province ${String.fromCharCode(65 + index)}`,
      })),
    };
    expect(validateA03Chat(value, metadata).province_analytics?.result.kind).toBe("province_breakdown");
    const forgedName = mutable(value);
    forgedName.province_analytics.result.rows[0].province_name = "Wrong province";
    expect(() => validateA03Chat(forgedName, metadata)).toThrow(/invalid A03/i);
    const forgedSource = mutable(value);
    forgedSource.province_analytics.result.source.data_status = "verified";
    expect(() => validateA03Chat(forgedSource, metadata)).toThrow(/invalid A03/i);
    const missingProvinceMetadata = structuredClone(metadata) as Record<string, unknown>;
    delete missingProvinceMetadata.provinces;
    const validateUncheckedMetadata = validateA03Chat as unknown as (input: unknown, uncheckedMetadata: unknown) => unknown;
    expect(() => validateUncheckedMetadata(value, missingProvinceMetadata)).toThrow(/invalid A03/i);
    const incompleteProvinceMetadata = structuredClone(metadata);
    incompleteProvinceMetadata.provinces.pop();
    expect(() => validateA03Chat(value, incompleteProvinceMetadata)).toThrow(/invalid A03/i);
    for (const mutation of ["code-format", "duplicate-code", "blank-name", "duplicate-name"] as const) {
      const invalidMetadata = structuredClone(metadata);
      if (mutation === "code-format") invalidMetadata.provinces[37].province_code = "X38";
      if (mutation === "duplicate-code") invalidMetadata.provinces[37].province_code = invalidMetadata.provinces[36].province_code;
      if (mutation === "blank-name") invalidMetadata.provinces[37].display_name = "   ";
      if (mutation === "duplicate-name") invalidMetadata.provinces[37].display_name = invalidMetadata.provinces[36].display_name;
      expect(() => validateA03Chat(value, invalidMetadata)).toThrow(/invalid A03/i);
    }
  });

  it.each([
    "extra",
    "duplicate",
    "sum",
    "rank",
    "order",
    "returnedRows",
    "coverage",
    "trace",
    "filters",
    "chart",
  ])("fails closed for %s mismatch", (mutation) => {
    const value = mutable(mutation === "rank" || mutation === "order" ? fixture.chat_top_5_cutoff_tie : fixture.chat_two_province_complete);
    const analytics = value.province_analytics;
    if (mutation === "extra") analytics.result.raw_sql = "forbidden";
    if (mutation === "duplicate") analytics.result.rows[1].province_code = analytics.result.rows[0].province_code;
    if (mutation === "sum") analytics.result.total = 999;
    if (mutation === "rank") analytics.result.rows[1].dense_rank = 7;
    if (mutation === "order") [analytics.result.rows[0], analytics.result.rows[1]] = [analytics.result.rows[1], analytics.result.rows[0]];
    if (mutation === "returnedRows") analytics.execution.returned_rows = 38;
    if (mutation === "coverage") analytics.result.coverage_state = "partial";
    if (mutation === "trace") value.execution_trace = mutable(oldTrace.chat_analytics.execution_trace);
    if (mutation === "filters") value.filters.province_codes = ["99"];
    if (mutation === "chart") value.chart = { type: "bar", title: "forged", series: [] };
    expect(() => validateA03Chat(value, metadataFor(value))).toThrow();
  });

  it.each([
    ["national exclusion count", "chat_two_province_complete", ["province_analytics", "result", "not_assigned_to_exactly_one_province_count"]],
    ["breakdown row count", "chat_two_province_complete", ["province_analytics", "result", "rows", 0, "count"]],
    ["breakdown total", "chat_two_province_complete", ["province_analytics", "result", "total"]],
    ["breakdown comparison", "chat_two_province_complete", ["province_analytics", "result", "comparison"]],
    ["ranking cutoff tie count", "chat_highest_top_1", ["province_analytics", "result", "cutoff_tie_count"]],
    ["execution metric value", "chat_two_province_complete", ["province_analytics", "execution", "metric_value"]],
  ] as const)("rejects missing required nullable %s", (_label, caseName, path) => {
    const value = mutable(fixture[caseName]);
    deleteNested(value, [...path]);
    expect(() => validateA03Chat(value, metadataFor(value))).toThrow(/invalid A03/i);
  });

  it("rejects one-character province codes across A03 result and execution fields", () => {
    const value = mutable(fixture.chat_three_province_comparison);
    value.filters.province_codes[0] = "1";
    value.province_analytics.result.requested_province_codes[0] = "1";
    value.province_analytics.result.rows[0].province_code = "1";
    value.province_analytics.result.comparison.highest_province_codes[0] = "1";
    value.province_analytics.execution.parameters.province_codes[0] = "1";
    expect(() => validateA03Chat(value, metadataFor(value))).toThrow(/invalid A03/i);
  });

  it.each([
    ["national exclusion count", ["province_analytics", "result", "not_assigned_to_exactly_one_province_count"]],
    ["breakdown row count", ["province_analytics", "result", "rows", 0, "count"]],
    ["breakdown total", ["province_analytics", "result", "total"]],
    ["execution metric value", ["province_analytics", "execution", "metric_value"]],
  ] as const)("rejects over-safe %s", (_label, path) => {
    const value = mutable(fixture.chat_two_province_complete);
    let current: Mutable = value;
    for (const segment of path.slice(0, -1)) current = current[segment] as Mutable;
    current[path.at(-1) as string | number] = Number.MAX_SAFE_INTEGER + 1;
    expect(() => validateA03Chat(value, metadataFor(value))).toThrow(/invalid A03/i);
  });

  it("rejects an over-safe comparison difference", () => {
    const value = mutable(fixture.chat_three_province_comparison);
    value.province_analytics.result.comparison.max_min_difference = Number.MAX_SAFE_INTEGER + 1;
    expect(() => validateA03Chat(value, metadataFor(value))).toThrow(/invalid A03/i);
  });

  it("rejects over-safe ranking counts", () => {
    const value = mutable(fixture.chat_highest_top_1);
    value.province_analytics.result.rows[0].count = Number.MAX_SAFE_INTEGER + 1;
    expect(() => validateA03Chat(value, metadataFor(value))).toThrow(/invalid A03/i);
  });

  it("keeps province result rows separate from monthly chart periods", () => {
    const topFiveValue = mutable(fixture.chat_top_5_cutoff_tie);
    const topFive = validateA03Chat(topFiveValue, metadataFor(topFiveValue));
    expect(topFive.chart).toBeNull();
    expect(topFive.province_analytics?.execution.returned_rows).toBe(6);
    expect(topFive.province_analytics?.result.rows).toHaveLength(6);
  });

  it("requires metadata and rejects unsafe source or coverage URLs", () => {
    const value = mutable(fixture.chat_partial_ranking);
    expect(() => validateA03Chat(value)).toThrow(/invalid A03/i);
    const unsafeSource = mutable(value);
    unsafeSource.province_analytics.result.source.url = "https://localhost/private";
    expect(() => validateA03Chat(unsafeSource, metadataFor(unsafeSource))).toThrow(/invalid A03/i);
    const unsafeCoverage = mutable(value);
    unsafeCoverage.province_analytics.result.coverage_issues[0].evidence_url = "https://192.168.1.2/private";
    expect(() => validateA03Chat(unsafeCoverage, metadataFor(unsafeCoverage))).toThrow(/invalid A03/i);
    for (const url of [
      "https://localhost./private",
      "https://service.local./private",
      "https://foo.localhost/private",
      "https://example.com./private",
      "https://foo..example.com/private",
      "https://./private",
    ]) {
      const unsafeLocalHostname = mutable(value);
      unsafeLocalHostname.province_analytics.result.source.url = url;
      expect(() => validateA03Chat(unsafeLocalHostname, metadataFor(unsafeLocalHostname))).toThrow(/invalid A03/i);
    }
    for (const url of [
      "https://[::]/private",
      "https://[::1]/private",
      "https://[::ffff:127.0.0.1]/private",
      "https://[::ffff:192.168.1.1]/private",
      "https://[fc00::1]/private",
      "https://[fdff::1]/private",
      "https://[fe80::1]/private",
      "https://[febf::1]/private",
      "https://[ff00::1]/private",
    ]) {
      const unsafeIpv6 = mutable(value);
      unsafeIpv6.province_analytics.result.source.url = url;
      expect(() => validateA03Chat(unsafeIpv6, metadataFor(unsafeIpv6))).toThrow(/invalid A03/i);
    }
  });

  it("validates every normative edge fixture branch", () => {
    for (const result of [
      edgeFixture.ordinal_result,
      edgeFixture.zero_count_result,
      edgeFixture.zero_count_empty_result,
      edgeFixture.ordinal_no_match_result,
      edgeFixture.all_38_result,
    ]) {
      const value = chatForRankingResult(result);
      expect(validateA03Chat(value, metadataFor(value)).province_analytics?.result).toEqual(result);
    }
    const unavailable = unavailableComparisonChat();
    expect(validateA03Chat(unavailable, metadataFor(unavailable)).province_analytics?.result).toEqual(edgeFixture.unavailable_breakdown_result);
    expect(unavailable.province_analytics.execution.parameters.comparison_requested).toBe(true);
    const comparisonNotRequested = mutable(unavailable);
    comparisonNotRequested.province_analytics.execution.parameters.comparison_requested = false;
    expect(validateA03Chat(comparisonNotRequested, metadataFor(comparisonNotRequested)).province_analytics?.result).toEqual(edgeFixture.unavailable_breakdown_result);
    const invalidComparisonFlag = mutable(unavailable);
    invalidComparisonFlag.province_analytics.execution.parameters.comparison_requested = "true";
    expect(() => validateA03Chat(invalidComparisonFlag, metadataFor(invalidComparisonFlag))).toThrow(/invalid A03/i);
  });

  it("requires canonical metadata for unavailable rankings and rank lookups", () => {
    const unavailable = mutable(fixture.chat_wholly_unavailable_ranking);
    const metadata = metadataFor(unavailable);
    const missingProvinceMetadata = structuredClone(metadata) as Record<string, unknown>;
    delete missingProvinceMetadata.provinces;
    const validateUncheckedMetadata = validateA03Chat as unknown as (input: unknown, uncheckedMetadata: unknown) => unknown;
    expect(() => validateUncheckedMetadata(unavailable, missingProvinceMetadata)).toThrow(/invalid A03/i);

    const incompleteMetadata = structuredClone(metadata);
    incompleteMetadata.provinces.pop();
    expect(() => validateA03Chat(unavailable, incompleteMetadata)).toThrow(/invalid A03/i);

    const duplicateMetadata = structuredClone(metadata);
    duplicateMetadata.provinces[37].province_code = duplicateMetadata.provinces[36].province_code;
    expect(() => validateA03Chat(unavailable, duplicateMetadata)).toThrow(/invalid A03/i);

    const noncanonicalLookup = mutable(unavailable);
    noncanonicalLookup.province_analytics.result.selection = { kind: "rank_lookup", province_code: "99" };
    noncanonicalLookup.province_analytics.execution.parameters.selection = { kind: "rank_lookup", province_code: "99" };
    expect(() => validateA03Chat(noncanonicalLookup, metadata)).toThrow(/invalid A03/i);
  });

  it("rejects an early top-N result and a missing cutoff tie", () => {
    const early = mutable(fixture.chat_top_5_cutoff_tie);
    early.province_analytics.result.rows = early.province_analytics.result.rows.slice(0, 1);
    early.province_analytics.execution.returned_rows = 1;
    expect(() => validateA03Chat(early, metadataFor(early))).toThrow(/invalid A03/i);
    const missingTie = mutable(fixture.chat_top_5_cutoff_tie);
    missingTie.province_analytics.result.rows.pop();
    missingTie.province_analytics.execution.returned_rows = 5;
    expect(() => validateA03Chat(missingTie, metadataFor(missingTie))).toThrow(/invalid A03/i);
  });
});
