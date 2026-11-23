import type { ChatResponse, CoverageIssue, MetadataResponse, SourceAttribution } from "./types";
import { validateChat } from "./validation";

export type A03CoverageState = "complete" | "partial" | "unavailable";
export type A03Direction = "highest" | "lowest";
export type A03Selection =
  | { kind: "top_n"; top_n: number }
  | { kind: "ordinal"; dense_rank: number }
  | { kind: "rank_lookup"; province_code: string }
  | { kind: "all" }
  | { kind: "zero_count" };

export interface A03ProvinceCountRow { province_code: string; province_name: string; province_order: number; count: number | null }
export interface A03ProvinceRankRow { province_code: string; province_name: string; province_order: number; count: number; dense_rank: number }
export interface A03ResultBase {
  metric: "satellite_hotspot_detections";
  product_id: string;
  date_from: string;
  date_to: string;
  source: SourceAttribution;
  coverage_state: A03CoverageState;
  is_complete: boolean;
  coverage_issues: CoverageIssue[];
  not_assigned_to_exactly_one_province_count: number | null;
}
export interface A03BreakdownResult extends A03ResultBase {
  kind: "province_breakdown";
  requested_province_codes: string[];
  total: number | null;
  rows: A03ProvinceCountRow[];
  comparison: { highest_province_codes: string[]; lowest_province_codes: string[]; max_min_difference: number } | null;
}
export interface A03RankingResult extends A03ResultBase {
  kind: "province_ranking";
  direction: A03Direction;
  selection: A03Selection;
  universe_size: 38;
  tie_policy: "dense_rank_include_cutoff_ties";
  selection_complete: true;
  cutoff_tie_count: number | null;
  rows: A03ProvinceRankRow[];
}
export type A03Result = A03BreakdownResult | A03RankingResult;

export type A03Parameters =
  | { kind: "multi_province_summary"; product_id: string; province_codes: string[]; date_from: string; date_to: string; comparison_requested: boolean }
  | { kind: "province_ranking"; product_id: string; date_from: string; date_to: string; direction: A03Direction; selection: A03Selection };

export interface A03ProvinceAnalytics {
  result: A03Result;
  execution: {
    operation_id: "hotspot_multi_province_summary_v1" | "hotspot_province_ranking_v1";
    parameters: A03Parameters;
    read_only: true;
    parameterized: true;
    returned_rows: number;
    metric_name: "satellite_hotspot_detections";
    metric_value: number | null;
  };
}

export interface A03ChatResponse extends ChatResponse {
  province_analytics?: A03ProvinceAnalytics | null;
}

type RecordValue = Record<string, unknown>;
const record = (value: unknown): value is RecordValue => typeof value === "object" && value !== null && !Array.isArray(value);
const exact = (value: RecordValue, keys: string[]) => Object.keys(value).every((key) => keys.includes(key)) && keys.every((key) => key in value);
const integer = (value: unknown, min = 0, max = Number.MAX_SAFE_INTEGER): value is number => typeof value === "number" && Number.isInteger(value) && value >= min && value <= max;
const nullableInteger = (value: unknown) => value === null || integer(value);
const provinceCode = (value: unknown): value is string => typeof value === "string" && /^\d{2}$/.test(value);
const unique = (values: string[]) => new Set(values).size === values.length;
const strings = (value: unknown): value is string[] => Array.isArray(value) && value.every((item) => typeof item === "string");

function safeHttps(value: unknown): boolean {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    const unbracketedHost = host.startsWith("[") && host.endsWith("]") ? host.slice(1, -1) : host;
    // Contract URLs are approved public HTTPS hostnames. Reject every numeric IP
    // literal fail-closed so alternate IPv4 spellings, IPv4-mapped IPv6, IPv6
    // unspecified/multicast, and private/local ranges cannot evade classification.
    // Terminal-dot and repeated-dot/root-like names are rejected, not normalized.
    if (url.protocol !== "https:" || url.username || url.password || unbracketedHost.endsWith(".") || unbracketedHost.includes("..")
      || unbracketedHost === "localhost" || unbracketedHost.endsWith(".localhost")
      || unbracketedHost === "local" || unbracketedHost.endsWith(".local") || unbracketedHost.includes(":")) return false;
    const ipv4 = unbracketedHost.split(".").map(Number);
    if (ipv4.length === 4 && ipv4.every((part) => Number.isInteger(part) && part >= 0 && part <= 255)) {
      return false;
    }
    return true;
  } catch { return false; }
}

function validSelection(value: unknown): value is A03Selection {
  if (!record(value) || typeof value.kind !== "string") return false;
  if (value.kind === "top_n") return exact(value, ["kind", "top_n"]) && integer(value.top_n, 1, 38);
  if (value.kind === "ordinal") return exact(value, ["kind", "dense_rank"]) && integer(value.dense_rank, 1, 38);
  if (value.kind === "rank_lookup") return exact(value, ["kind", "province_code"]) && provinceCode(value.province_code);
  return (value.kind === "all" || value.kind === "zero_count") && exact(value, ["kind"]);
}

function validCoverageIssue(value: unknown): boolean {
  return record(value) && exact(value, ["date_utc", "coverage_status", "evidence_url", "note"])
    && typeof value.date_utc === "string" && ["known_satellite_gap", "unknown"].includes(String(value.coverage_status))
    && (value.evidence_url === null || safeHttps(value.evidence_url))
    && (value.note === null || typeof value.note === "string")
    && (value.coverage_status !== "known_satellite_gap" || typeof value.evidence_url === "string");
}

function validSource(value: unknown): boolean {
  return record(value) && exact(value, ["provider", "dataset_version", "data_status", "url", "attribution"])
    && typeof value.provider === "string" && typeof value.dataset_version === "string"
    && ["mock", "verified"].includes(String(value.data_status)) && safeHttps(value.url)
    && typeof value.attribution === "string";
}

function validBase(value: RecordValue): boolean {
  if (value.metric !== "satellite_hotspot_detections" || typeof value.product_id !== "string" || typeof value.date_from !== "string" || typeof value.date_to !== "string" || value.date_to < value.date_from || !validSource(value.source)
    || !["complete", "partial", "unavailable"].includes(String(value.coverage_state)) || typeof value.is_complete !== "boolean"
    || !Array.isArray(value.coverage_issues) || value.coverage_issues.length > 366 || !value.coverage_issues.every(validCoverageIssue)
    || !nullableInteger(value.not_assigned_to_exactly_one_province_count)) return false;
  const issues = value.coverage_issues as Array<{ date_utc: string }>;
  const issueDates = issues.map((issue) => issue.date_utc);
  const dateFrom = value.date_from as string;
  const dateTo = value.date_to as string;
  const requestedDays = Math.floor((Date.parse(`${dateTo}T00:00:00Z`) - Date.parse(`${dateFrom}T00:00:00Z`)) / 86400000) + 1;
  if (!Number.isInteger(requestedDays) || requestedDays < 1 || !unique(issueDates) || issueDates.some((date) => date < dateFrom || date > dateTo)) return false;
  if (value.coverage_state === "complete") return value.is_complete && issues.length === 0;
  if (value.coverage_state === "partial") return !value.is_complete && issues.length > 0 && issues.length < requestedDays;
  return !value.is_complete && issues.length === requestedDays && value.not_assigned_to_exactly_one_province_count === null;
}

function metadataRowsValid(rows: Array<{ province_code: string; province_name: string; province_order: number }>, provinces?: Array<{ province_code: string; display_name: string }>): boolean {
  if (!Array.isArray(provinces) || provinces.length !== 38) return false;
  if (!provinces.every((province) => /^\d{2}$/.test(province.province_code) && province.display_name.trim().length >= 1 && province.display_name.length <= 100)
    || !unique(provinces.map((province) => province.province_code))
    || !unique(provinces.map((province) => province.display_name))) return false;
  return rows.every((row) => provinces[row.province_order - 1]?.province_code === row.province_code && provinces[row.province_order - 1]?.display_name === row.province_name);
}

function validBreakdown(value: RecordValue, provinces?: Array<{ province_code: string; display_name: string }>): boolean {
  const keys = ["kind", "metric", "product_id", "date_from", "date_to", "source", "coverage_state", "is_complete", "coverage_issues", "not_assigned_to_exactly_one_province_count", "requested_province_codes", "total", "rows", "comparison"];
  const requested = value.requested_province_codes;
  if (!exact(value, keys) || !validBase(value) || !strings(requested) || !requested.every(provinceCode) || requested.length < 2 || requested.length > 38 || !unique(requested)
    || !nullableInteger(value.total) || !Array.isArray(value.rows) || value.rows.length !== requested.length) return false;
  const rows = value.rows;
  if (!rows.every((row, index) => record(row) && exact(row, ["province_code", "province_name", "province_order", "count"])
    && row.province_code === requested[index] && provinceCode(row.province_code) && typeof row.province_name === "string" && row.province_name.length >= 1 && row.province_name.length <= 100
    && integer(row.province_order, 1, 38) && nullableInteger(row.count))) return false;
  const typedRows = rows as A03ProvinceCountRow[];
  if (!unique(typedRows.map((row) => row.province_code)) || !unique(typedRows.map((row) => String(row.province_order))) || !metadataRowsValid(typedRows, provinces)) return false;
  if (value.coverage_state === "unavailable") return value.total === null && typedRows.every((row) => row.count === null) && value.comparison === null;
  if (typedRows.some((row) => row.count === null)) return false;
  const counts = typedRows.map((row) => row.count as number);
  if (value.total !== counts.reduce((sum, count) => sum + count, 0)) return false;
  if (value.comparison === null) return true;
  if (!record(value.comparison) || !exact(value.comparison, ["highest_province_codes", "lowest_province_codes", "max_min_difference"]) || !strings(value.comparison.highest_province_codes) || !strings(value.comparison.lowest_province_codes) || !integer(value.comparison.max_min_difference)) return false;
  const high = Math.max(...counts); const low = Math.min(...counts);
  return JSON.stringify(value.comparison.highest_province_codes) === JSON.stringify(typedRows.filter((row) => row.count === high).map((row) => row.province_code))
    && JSON.stringify(value.comparison.lowest_province_codes) === JSON.stringify(typedRows.filter((row) => row.count === low).map((row) => row.province_code))
    && value.comparison.max_min_difference === high - low;
}

function validRanking(value: RecordValue, provinces?: Array<{ province_code: string; display_name: string }>): boolean {
  const keys = ["kind", "metric", "product_id", "date_from", "date_to", "source", "coverage_state", "is_complete", "coverage_issues", "not_assigned_to_exactly_one_province_count", "direction", "selection", "universe_size", "tie_policy", "selection_complete", "cutoff_tie_count", "rows"];
  if (!exact(value, keys) || !validBase(value) || !["highest", "lowest"].includes(String(value.direction)) || !validSelection(value.selection) || value.universe_size !== 38 || value.tie_policy !== "dense_rank_include_cutoff_ties" || value.selection_complete !== true || (value.cutoff_tie_count !== null && !integer(value.cutoff_tie_count, 1, 38)) || !Array.isArray(value.rows) || value.rows.length > 38) return false;
  if (!value.rows.every((row) => record(row) && exact(row, ["province_code", "province_name", "province_order", "count", "dense_rank"])
    && provinceCode(row.province_code) && typeof row.province_name === "string" && row.province_name.length >= 1 && row.province_name.length <= 100
    && integer(row.province_order, 1, 38) && integer(row.count) && integer(row.dense_rank, 1, 38))) return false;
  const rows = value.rows as A03ProvinceRankRow[];
  const selection = value.selection as A03Selection;
  if (selection.kind === "zero_count" && value.direction !== "lowest") return false;
  if (!unique(rows.map((row) => row.province_code)) || !unique(rows.map((row) => String(row.province_order))) || !metadataRowsValid(rows, provinces)) return false;
  if (selection.kind === "rank_lookup" && !provinces?.some((province) => province.province_code === selection.province_code)) return false;
  if (value.coverage_state === "unavailable") return rows.length === 0 && value.cutoff_tie_count === null;
  for (let index = 1; index < rows.length; index += 1) {
    const before = rows[index - 1]; const current = rows[index];
    const ordered = value.direction === "highest" ? before.count >= current.count : before.count <= current.count;
    if (!ordered || (before.count === current.count && (before.dense_rank !== current.dense_rank || before.province_order >= current.province_order))
      || (before.count !== current.count && current.dense_rank !== before.dense_rank + 1)) return false;
  }
  if (selection.kind === "top_n") {
    if (rows.length === 0 || rows[0].dense_rank !== 1 || rows.some((row) => row.dense_rank > selection.top_n)) return false;
    const lastRank = rows.at(-1)?.dense_rank;
    return (rows.length === 38 || lastRank === selection.top_n) && value.cutoff_tie_count === rows.filter((row) => row.dense_rank === lastRank).length;
  }
  if (selection.kind === "ordinal") return rows.every((row) => row.dense_rank === selection.dense_rank) && value.cutoff_tie_count === (rows.length || null);
  if (selection.kind === "rank_lookup") return value.cutoff_tie_count === null && rows.length === 1 && rows[0].province_code === selection.province_code;
  if (selection.kind === "all") return value.cutoff_tie_count === null && rows.length === 38 && rows[0].dense_rank === 1;
  return value.cutoff_tie_count === (rows.length || null) && rows.every((row) => row.count === 0 && row.dense_rank === 1);
}

function validExecution(value: unknown, result: A03Result): value is A03ProvinceAnalytics["execution"] {
  if (!record(value) || !exact(value, ["operation_id", "parameters", "read_only", "parameterized", "returned_rows", "metric_name", "metric_value"])
    || value.read_only !== true || value.parameterized !== true || !integer(value.returned_rows, 0, 38) || value.returned_rows !== result.rows.length
    || value.metric_name !== result.metric || !nullableInteger(value.metric_value) || !record(value.parameters)) return false;
  const params = value.parameters;
  if (params.product_id !== result.product_id || params.date_from !== result.date_from || params.date_to !== result.date_to) return false;
  if (result.kind === "province_breakdown") {
    return value.operation_id === "hotspot_multi_province_summary_v1" && exact(params, ["kind", "product_id", "province_codes", "date_from", "date_to", "comparison_requested"])
      && params.kind === "multi_province_summary" && JSON.stringify(params.province_codes) === JSON.stringify(result.requested_province_codes)
      && typeof params.comparison_requested === "boolean"
      && (result.coverage_state === "unavailable" || params.comparison_requested === (result.comparison !== null)) && value.metric_value === result.total;
  }
  return value.operation_id === "hotspot_province_ranking_v1" && exact(params, ["kind", "product_id", "date_from", "date_to", "direction", "selection"])
    && params.kind === "province_ranking" && params.direction === result.direction && JSON.stringify(params.selection) === JSON.stringify(result.selection)
    && value.metric_value === (result.rows[0]?.count ?? null);
}

export function validateA03Chat(value: unknown, metadata?: Pick<MetadataResponse, "products" | "provinces" | "source" | "data_status">): A03ChatResponse {
  const legacy = validateChat(value) as A03ChatResponse;
  if (!record(value) || value.province_analytics === undefined || value.province_analytics === null) return legacy;
  if (!metadata) throw new Error("The API returned an invalid A03 chat response.");
  if (!record(value.province_analytics) || !exact(value.province_analytics, ["result", "execution"]) || !record(value.province_analytics.result)) throw new Error("The API returned an invalid A03 chat response.");
  const resultValue = value.province_analytics.result;
  const resultValid = resultValue.kind === "province_breakdown" ? validBreakdown(resultValue, metadata.provinces) : resultValue.kind === "province_ranking" && validRanking(resultValue, metadata.provinces);
  if (!resultValid) throw new Error("The API returned an invalid A03 chat response.");
  const result = resultValue as unknown as A03Result;
  if (!validExecution(value.province_analytics.execution, result) || !["analytics", "combined"].includes(String(value.mode)) || !record(value.filters) || value.filters.date_from !== result.date_from || value.filters.date_to !== result.date_to || value.chart !== null) throw new Error("The API returned an invalid A03 chat response.");
  const sameSource = metadata.source.provider === result.source.provider && metadata.source.dataset_version === result.source.dataset_version && metadata.source.data_status === result.source.data_status && metadata.source.url === result.source.url && metadata.source.attribution === result.source.attribution;
  if (metadata.data_status !== result.source.data_status || !sameSource || !metadata.products.some((product) => product.product_id === result.product_id)) throw new Error("The API returned an invalid A03 chat response.");
  const expectedCodes = result.kind === "province_breakdown" ? result.requested_province_codes : [];
  if (JSON.stringify(value.filters.province_codes) !== JSON.stringify(expectedCodes)) throw new Error("The API returned an invalid A03 chat response.");
  if (record(value.execution_trace)) {
    const steps = Array.isArray(value.execution_trace.steps) ? value.execution_trace.steps : [];
    if (value.mode !== "combined" || steps.some((step) => record(step) && step.kind === "analytics_query")) throw new Error("The API returned an invalid A03 chat response.");
  }
  const expectedMetric = result.kind === "province_breakdown" ? result.total : (result.rows[0]?.count ?? null);
  if (Array.isArray(value.metrics)) {
    const matches = value.metrics.filter((metric) => record(metric) && metric.name === "satellite_hotspot_detections");
    if (matches.length !== 1 || matches[0].value !== expectedMetric) throw new Error("The API returned an invalid A03 chat response.");
  }
  if (value.mode === "analytics" && record(value.usage) && value.usage.llm_calls !== 0) throw new Error("The API returned an invalid A03 chat response.");
  return legacy;
}
