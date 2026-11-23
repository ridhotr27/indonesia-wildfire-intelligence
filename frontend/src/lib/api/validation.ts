import { ApiError } from "./errors";
import type { ChatResponse, HotspotFeatureCollection, MetadataResponse, SummaryResponse, YearComparisonResponse } from "./types";

type RecordValue = Record<string, unknown>;

function record(value: unknown): value is RecordValue {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function strings(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function requestId(value: unknown): string | undefined {
  return record(value) && typeof value.request_id === "string" ? value.request_id : undefined;
}

function invalid(kind: string, value: unknown): never {
  throw new ApiError(`The API returned an invalid ${kind} response.`, "DEPENDENCY_UNAVAILABLE", 503, requestId(value));
}

function validSource(value: unknown): boolean {
  return record(value)
    && typeof value.provider === "string"
    && typeof value.dataset_version === "string"
    && ["mock", "verified"].includes(String(value.data_status))
    && typeof value.url === "string"
    && typeof value.attribution === "string";
}

function httpsUrl(value: unknown): boolean {
  if (typeof value !== "string") return false;
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase();
    if (url.protocol !== "https:" || host === "localhost" || host.endsWith(".local") || host === "::1") return false;
    const ipv4 = host.split(".").map(Number);
    if (ipv4.length === 4 && ipv4.every((part) => Number.isInteger(part) && part >= 0 && part <= 255)) {
      if (ipv4[0] === 10 || ipv4[0] === 127 || ipv4[0] === 0 || (ipv4[0] === 169 && ipv4[1] === 254) || (ipv4[0] === 192 && ipv4[1] === 168) || (ipv4[0] === 172 && ipv4[1] >= 16 && ipv4[1] <= 31)) return false;
    }
    return true;
  } catch {
    return false;
  }
}

function validCoverageIssue(value: unknown): boolean {
  return record(value)
    && typeof value.date_utc === "string"
    && ["known_satellite_gap", "unknown"].includes(String(value.coverage_status))
    && (value.evidence_url === null || typeof value.evidence_url === "string")
    && (value.note === null || typeof value.note === "string");
}

function validFilters(value: unknown): boolean {
  return record(value)
    && strings(value.province_codes)
    && typeof value.date_from === "string"
    && typeof value.date_to === "string";
}

function validPoint(value: unknown): boolean {
  return record(value)
    && typeof value.period === "string"
    && (value.count === null || (typeof value.count === "number" && Number.isInteger(value.count) && value.count >= 0))
    && typeof value.is_complete === "boolean"
    && Array.isArray(value.coverage_issues)
    && value.coverage_issues.every(validCoverageIssue);
}

export function validateYearComparison(value: unknown): YearComparisonResponse {
  if (!record(value)
    || typeof value.request_id !== "string"
    || value.operation_id !== "hotspot_year_comparison_v1"
    || value.metric !== "satellite_hotspot_detections"
    || typeof value.product_id !== "string"
    || typeof value.province_code !== "string"
    || !Array.isArray(value.years)
    || value.years.length < 2
    || value.years.length > 3
    || value.years.some((year) => ![2023, 2024, 2025].includes(Number(year)))
    || value.years.some((year, index, years) => index > 0 && Number(year) <= Number(years[index - 1]))
    || !Array.isArray(value.points)
    || value.points.length !== value.years.length
    || !value.points.every((point, index) => record(point)
      && point.year === (value.years as unknown[])[index]
      && (point.count === null || boundedInteger(point.count, 0, Number.MAX_SAFE_INTEGER))
      && typeof point.is_complete === "boolean"
      && Array.isArray(point.coverage_issues)
      && point.coverage_issues.every(validCoverageIssue)
      && (!point.is_complete || (point.count !== null && point.coverage_issues.length === 0)))
    || !validSource(value.source)
    || value.caveat !== "Hotspot detections are not confirmed wildfires.") invalid("year comparison", value);
  return value as unknown as YearComparisonResponse;
}

function exactKeys(value: RecordValue, allowed: string[]): boolean {
  return Object.keys(value).every((key) => allowed.includes(key));
}

function boundedInteger(value: unknown, minimum: number, maximum: number): boolean {
  return typeof value === "number" && Number.isInteger(value) && value >= minimum && value <= maximum;
}

function validTraceDetails(value: unknown, kind: string): boolean {
  if (!record(value) || value.kind !== kind) return false;
  if (kind === "route_selection") return exactKeys(value, ["kind", "route"]) && ["analytics", "rag", "combined", "unsupported"].includes(String(value.route));
  if (kind === "filter_resolution") return exactKeys(value, ["kind", "province_codes", "date_from", "date_to", "province_source", "date_from_source", "date_to_source", "reason_codes", "outcome"])
    && strings(value.province_codes) && value.province_codes.length <= 38
    && (value.date_from === null || typeof value.date_from === "string") && (value.date_to === null || typeof value.date_to === "string")
    && [value.province_source, value.date_from_source, value.date_to_source].every((item) => ["message", "ui_context", "absent"].includes(String(item)))
    && Array.isArray(value.reason_codes) && value.reason_codes.length <= 5 && value.reason_codes.every((item) => ["missing_province", "missing_date_range", "ambiguous_province", "conflicting_province", "conflicting_date_range", "invalid_date_range"].includes(String(item)))
    && ["resolved", "needs_clarification", "invalid", "not_applicable"].includes(String(value.outcome));
  if (kind === "analytics_query") {
    if (!exactKeys(value, ["kind", "operation_id", "parameters", "read_only", "returned_rows", "metric_name", "metric_value"])
      || value.read_only !== true || !boundedInteger(value.returned_rows, 0, 5000)
      || (value.metric_name !== undefined && value.metric_name !== null && value.metric_name !== "satellite_hotspot_detections")
      || (value.metric_value !== undefined && value.metric_value !== null && !boundedInteger(value.metric_value, 0, Number.MAX_SAFE_INTEGER))) return false;
    if (value.operation_id === "hotspot_year_comparison_v1") {
      if (!record(value.parameters) || !exactKeys(value.parameters, ["province_code", "years"]) || typeof value.parameters.province_code !== "string" || !Array.isArray(value.parameters.years)) return false;
      const years = value.parameters.years;
      return years.length >= 2 && years.length <= 3 && years.every((year) => [2023, 2024, 2025].includes(Number(year)))
        && years.every((year, index) => index === 0 || Number(year) > Number(years[index - 1])) && value.returned_rows === years.length && value.metric_value === null;
    }
    return ["hotspot_summary_v1", "hotspot_trend_v1", "hotspot_map_v1"].includes(String(value.operation_id)) && validFilters(value.parameters);
  }
  if (kind === "vector_retrieval") return exactKeys(value, ["kind", "provider", "embedding_model", "collection", "top_k", "returned_count", "items"])
    && value.provider === "local" && typeof value.embedding_model === "string" && value.embedding_model.length >= 1 && value.embedding_model.length <= 100
    && typeof value.collection === "string" && value.collection.length >= 1 && value.collection.length <= 100 && boundedInteger(value.top_k, 1, 5)
    && boundedInteger(value.returned_count, 0, 5) && Array.isArray(value.items) && value.items.length === value.returned_count && value.items.length <= 5
    && value.items.every((item, index) => record(item) && exactKeys(item, ["chunk_id", "title", "url", "rank"]) && typeof item.chunk_id === "string" && item.chunk_id.length <= 128 && typeof item.title === "string" && item.title.length <= 200 && typeof item.url === "string" && httpsUrl(item.url) && item.url.length <= 500 && item.rank === index + 1);
  if (kind === "local_generation") return exactKeys(value, ["kind", "provider", "model", "input_passage_count", "model_calls"]) && value.provider === "ollama" && typeof value.model === "string" && value.model.length >= 1 && value.model.length <= 100 && boundedInteger(value.input_passage_count, 0, 5) && boundedInteger(value.model_calls, 1, 2);
  if (kind === "citation_validation") return exactKeys(value, ["kind", "candidate_count", "accepted_count", "outcome"]) && typeof value.candidate_count === "number" && typeof value.accepted_count === "number" && boundedInteger(value.candidate_count, 0, 5) && boundedInteger(value.accepted_count, 0, 5) && value.accepted_count <= value.candidate_count && ["passed", "abstained", "failed"].includes(String(value.outcome));
  if (kind === "abstention") return exactKeys(value, ["kind", "reason_code"]) && ["missing_province", "missing_date_range", "unsupported_intent", "insufficient_evidence"].includes(String(value.reason_code));
  return false;
}

function validExecutionTrace(value: unknown): boolean {
  if (!record(value) || !exactKeys(value, ["trace_version", "route", "status", "steps"]) || value.trace_version !== "1.0" || !["analytics", "rag", "combined", "unsupported"].includes(String(value.route)) || !["complete", "abstained", "partial"].includes(String(value.status)) || !Array.isArray(value.steps) || value.steps.length < 1 || value.steps.length > 8) return false;
  return value.steps.every((step, index) => record(step) && exactKeys(step, ["sequence", "kind", "status", "label", "duration_ms", "details"])
    && step.sequence === index + 1 && ["route_selection", "filter_resolution", "analytics_query", "vector_retrieval", "local_generation", "citation_validation", "abstention"].includes(String(step.kind))
    && ["complete", "abstained", "failed"].includes(String(step.status)) && typeof step.label === "string" && step.label.length >= 1 && step.label.length <= 200
    && (step.duration_ms === undefined || step.duration_ms === null || boundedInteger(step.duration_ms, 0, 300000)) && validTraceDetails(step.details, String(step.kind)));
}

export function validateMetadata(value: unknown): MetadataResponse {
  if (!record(value)
    || typeof value.request_id !== "string"
    || value.api_version !== "1.0.0"
    || !Array.isArray(value.products)
    || !value.products.every((item) => record(item) && typeof item.product_id === "string" && typeof item.display_name === "string")
    || !Array.isArray(value.provinces)
    || !value.provinces.every((item) => record(item) && typeof item.province_code === "string" && typeof item.display_name === "string")
    || !record(value.coverage)
    || typeof value.coverage.date_min !== "string"
    || typeof value.coverage.date_max !== "string"
    || !strings(value.coverage.known_unavailable_dates)
    || !validSource(value.source)
    || (value.data_freshness_at !== null && typeof value.data_freshness_at !== "string")
    || !["mock", "verified"].includes(String(value.data_status))
    || !record(value.source)
    || value.source.data_status !== value.data_status) invalid("metadata", value);
  return value as unknown as MetadataResponse;
}

export function validateSummary(value: unknown): SummaryResponse {
  if (!record(value)
    || typeof value.request_id !== "string"
    || value.metric !== "satellite_hotspot_detections"
    || typeof value.product_id !== "string"
    || !validFilters(value.filters)
    || (value.total !== null && (typeof value.total !== "number" || !Number.isInteger(value.total) || value.total < 0))
    || typeof value.is_complete !== "boolean"
    || !Array.isArray(value.coverage_issues)
    || !value.coverage_issues.every(validCoverageIssue)
    || !strings(value.warnings)
    || !Array.isArray(value.series)
    || !value.series.every(validPoint)
    || !validSource(value.source)
    || typeof value.caveat !== "string") invalid("summary", value);
  return value as unknown as SummaryResponse;
}

function validFeature(value: unknown): boolean {
  if (!record(value) || value.type !== "Feature" || !record(value.geometry) || value.geometry.type !== "Point" || !Array.isArray(value.geometry.coordinates) || value.geometry.coordinates.length !== 2 || !value.geometry.coordinates.every((coordinate) => typeof coordinate === "number" && Number.isFinite(coordinate)) || !record(value.properties)) return false;
  const properties = value.properties;
  const [longitude, latitude] = value.geometry.coordinates as number[];
  return longitude >= -180 && longitude <= 180 && latitude >= -90 && latitude <= 90
    && typeof properties.observation_id === "string"
    && typeof properties.acquired_at_utc === "string"
    && typeof properties.product_id === "string"
    && typeof properties.province_code === "string"
    && ["l", "n", "h"].includes(String(properties.confidence_code))
    && typeof properties.frp_mw === "number"
    && properties.frp_mw >= 0
    && ["D", "N"].includes(String(properties.daynight_code));
}

export function validateHotspots(value: unknown): HotspotFeatureCollection {
  if (!record(value) || value.type !== "FeatureCollection" || !Array.isArray(value.features) || !value.features.every(validFeature) || !record(value.metadata)) invalid("map", value);
  const metadata = value.metadata;
  if (typeof metadata.request_id !== "string"
    || typeof metadata.product_id !== "string"
    || !validFilters(metadata.filters)
    || typeof metadata.truncated !== "boolean"
    || typeof metadata.returned !== "number"
    || metadata.returned !== value.features.length
    || typeof metadata.limit !== "number"
    || typeof metadata.is_complete !== "boolean"
    || !Array.isArray(metadata.coverage_issues)
    || !metadata.coverage_issues.every(validCoverageIssue)
    || !validSource(metadata.source)
    || typeof metadata.caveat !== "string") invalid("map", value);
  return value as unknown as HotspotFeatureCollection;
}

export function validateChat(value: unknown): ChatResponse {
  if (!record(value)
    || typeof value.request_id !== "string"
    || typeof value.answer !== "string"
    || !["analytics", "rag", "combined", "unsupported"].includes(String(value.mode))
    || (value.filters !== null && !validFilters(value.filters))
    || (value.metrics !== null && (!Array.isArray(value.metrics) || !value.metrics.every((item) => record(item) && typeof item.name === "string" && (item.value === null || typeof item.value === "number") && typeof item.unit === "string")))
    || (value.chart !== null && (!record(value.chart) || !["line", "bar"].includes(String(value.chart.type)) || typeof value.chart.title !== "string" || !Array.isArray(value.chart.series) || !value.chart.series.every(validPoint)))
    || (value.map !== null && (!record(value.map) || value.map.type !== "FeatureCollection" || !Array.isArray(value.map.features) || !value.map.features.every(validFeature)))
    || !Array.isArray(value.citations)
    || !value.citations.every((item) => record(item) && typeof item.title === "string" && httpsUrl(item.url) && typeof item.chunk_id === "string")
    || !strings(value.limitations)
    || !record(value.usage)
    || typeof value.usage.llm_calls !== "number"
    || !Number.isInteger(value.usage.llm_calls)
    || value.usage.llm_calls < 0
    || (value.year_comparison !== undefined && value.year_comparison !== null && (() => { try { validateYearComparison(value.year_comparison); return false; } catch { return true; } })())
    || (value.execution_trace !== undefined && value.execution_trace !== null && !validExecutionTrace(value.execution_trace))) invalid("chat", value);
  if (record(value.execution_trace)) {
    const trace = value.execution_trace;
    if (trace.route !== value.mode || !Array.isArray(trace.steps)) invalid("chat", value);
    const details = trace.steps.filter(record).map((step) => step.details).filter(record);
    const analytics = details.filter((item) => item.kind === "analytics_query");
    const responseFilters = value.filters;
    if (analytics.some((item) => {
      if (!record(responseFilters) || !record(item.parameters)) return true;
      if (item.operation_id === "hotspot_year_comparison_v1") return !record(value.year_comparison)
        || item.parameters.province_code !== value.year_comparison.province_code
        || JSON.stringify(item.parameters.years) !== JSON.stringify(value.year_comparison.years)
        || JSON.stringify(responseFilters.province_codes) !== JSON.stringify([item.parameters.province_code]);
      return JSON.stringify(item.parameters) !== JSON.stringify(responseFilters);
    })) invalid("chat", value);
    const chart = value.chart;
    const chartSeries = record(chart) ? chart.series : null;
    if (Array.isArray(chartSeries) && analytics.some((item) => item.returned_rows !== chartSeries.length)) invalid("chat", value);
    if (analytics.some((item) => {
      if (item.operation_id === "hotspot_year_comparison_v1" || typeof item.metric_name !== "string" || item.metric_value === undefined) return false;
      if (!Array.isArray(value.metrics)) return true;
      const matchingMetrics = value.metrics.filter((metric) => record(metric) && metric.name === item.metric_name);
      return matchingMetrics.length !== 1 || !Object.is(matchingMetrics[0].value, item.metric_value);
    })) invalid("chat", value);
    const calls = details.filter((item) => item.kind === "local_generation").reduce((total, item) => total + (typeof item.model_calls === "number" ? item.model_calls : 0), 0);
    if (calls !== value.usage.llm_calls) invalid("chat", value);
    const retrieved = new Set(details.filter((item) => item.kind === "vector_retrieval").flatMap((item) => Array.isArray(item.items) ? item.items.filter(record).map((entry) => entry.chunk_id) : []));
    if (value.citations.some((item) => record(item) && !retrieved.has(item.chunk_id))) invalid("chat", value);
  }
  return value as unknown as ChatResponse;
}
