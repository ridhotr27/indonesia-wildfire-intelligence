export type ApiMode = "mock" | "real";
export type GroupBy = "month";
export type ChatMode = "analytics" | "rag" | "combined" | "unsupported";
export type DataStatus = "mock" | "verified";
export type CoverageStatus = "known_satellite_gap" | "unknown";

export interface Province {
  province_code: string;
  display_name: string;
}

export interface Product {
  product_id: string;
  display_name: string;
}

export interface SourceAttribution {
  provider: string;
  dataset_version: string;
  data_status: DataStatus;
  url: string;
  attribution: string;
}

export interface CoverageIssue {
  date_utc: string;
  coverage_status: CoverageStatus;
  evidence_url: string | null;
  note: string | null;
}

export interface MetadataResponse {
  request_id: string;
  api_version: "1.0.0";
  products: Product[];
  provinces: Province[];
  coverage: { date_min: string; date_max: string; known_unavailable_dates: string[] };
  source: SourceAttribution;
  data_freshness_at: string | null;
  data_status: DataStatus;
}

export interface AnalysisFilters {
  province_codes: string[];
  date_from: string;
  date_to: string;
}

export interface SummaryRequest extends AnalysisFilters {
  product_id: string;
  group_by: GroupBy;
}

export interface SummaryPoint {
  period: string;
  count: number | null;
  is_complete: boolean;
  coverage_issues: CoverageIssue[];
}

export interface SummaryResponse {
  request_id: string;
  metric: "satellite_hotspot_detections";
  product_id: string;
  filters: AnalysisFilters;
  total: number | null;
  is_complete: boolean;
  coverage_issues: CoverageIssue[];
  warnings: string[];
  series: SummaryPoint[];
  source: SourceAttribution;
  caveat: string;
}

export type SupportedYear = 2023 | 2024 | 2025;

export interface YearComparisonRequest {
  product_id: string;
  province_code: string;
  years: SupportedYear[];
}

export interface YearComparisonPoint {
  year: SupportedYear;
  count: number | null;
  is_complete: boolean;
  coverage_issues: CoverageIssue[];
}

export interface YearComparisonResponse {
  request_id: string;
  operation_id: "hotspot_year_comparison_v1";
  metric: "satellite_hotspot_detections";
  product_id: string;
  province_code: string;
  years: SupportedYear[];
  points: YearComparisonPoint[];
  source: SourceAttribution;
  caveat: "Hotspot detections are not confirmed wildfires.";
}

export interface HotspotProperties {
  observation_id: string;
  acquired_at_utc: string;
  province_code: string;
  confidence_code: "l" | "n" | "h";
  frp_mw: number;
  daynight_code: "D" | "N";
  product_id: string;
}

export interface HotspotFeature {
  type: "Feature";
  id?: string;
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: HotspotProperties;
}

export interface HotspotFeatureCollection {
  type: "FeatureCollection";
  features: HotspotFeature[];
  metadata: {
    request_id: string;
    product_id: string;
    filters: AnalysisFilters;
    truncated: boolean;
    returned: number;
    limit: number;
    is_complete: boolean;
    coverage_issues: CoverageIssue[];
    source: SourceAttribution;
    caveat: "Hotspot detections are not confirmed wildfires.";
  };
}

export interface Citation {
  title: string;
  url: string;
  chunk_id: string;
}

export interface ChatRequest {
  message: string;
  product_id: string;
  context: { province_code: string | null; date_from: string | null; date_to: string | null };
}

export interface ChatChart {
  type: "line" | "bar";
  title: string;
  series: SummaryPoint[];
}

export interface ChatMap {
  type: "FeatureCollection";
  features: HotspotFeature[];
}

export type TraceRoute = ChatMode;
export type TraceSource = "message" | "ui_context" | "absent";
export type TraceStepStatus = "complete" | "abstained" | "failed";
export type TraceReasonCode = "missing_province" | "missing_date_range" | "ambiguous_province" | "conflicting_province" | "conflicting_date_range" | "invalid_date_range";

export type ExecutionTraceDetails =
  | { kind: "route_selection"; route: TraceRoute }
  | { kind: "filter_resolution"; province_codes: string[]; date_from: string | null; date_to: string | null; province_source: TraceSource; date_from_source: TraceSource; date_to_source: TraceSource; reason_codes: TraceReasonCode[]; outcome: "resolved" | "needs_clarification" | "invalid" | "not_applicable" }
  | { kind: "analytics_query"; operation_id: "hotspot_summary_v1" | "hotspot_trend_v1" | "hotspot_map_v1"; parameters: AnalysisFilters; read_only: true; returned_rows: number; metric_name?: "satellite_hotspot_detections" | null; metric_value?: number | null }
  | { kind: "analytics_query"; operation_id: "hotspot_year_comparison_v1"; parameters: { province_code: string; years: SupportedYear[] }; read_only: true; returned_rows: number; metric_name?: "satellite_hotspot_detections" | null; metric_value?: null }
  | { kind: "vector_retrieval"; provider: "local"; embedding_model: string; collection: string; top_k: number; returned_count: number; items: { chunk_id: string; title: string; url: string; rank: number }[] }
  | { kind: "local_generation"; provider: "ollama"; model: string; input_passage_count: number; model_calls: number }
  | { kind: "citation_validation"; candidate_count: number; accepted_count: number; outcome: "passed" | "abstained" | "failed" }
  | { kind: "abstention"; reason_code: "missing_province" | "missing_date_range" | "unsupported_intent" | "insufficient_evidence" };

export interface ExecutionTraceStep {
  sequence: number;
  kind: ExecutionTraceDetails["kind"];
  status: TraceStepStatus;
  label: string;
  duration_ms?: number | null;
  details: ExecutionTraceDetails;
}

export interface ExecutionTrace {
  trace_version: "1.0";
  route: TraceRoute;
  status: "complete" | "abstained" | "partial";
  steps: ExecutionTraceStep[];
}

export interface ChatResponse {
  request_id: string;
  answer: string;
  mode: ChatMode;
  filters: AnalysisFilters | null;
  metrics: { name: string; value: number | null; unit: string }[] | null;
  chart: ChatChart | null;
  map: ChatMap | null;
  citations: Citation[];
  limitations: string[];
  usage: { llm_calls: number };
  execution_trace?: ExecutionTrace | null;
  year_comparison?: YearComparisonResponse | null;
}

export type ApiErrorCode = "INVALID_FILTER" | "VALIDATION_ERROR" | "RATE_LIMITED" | "DEPENDENCY_UNAVAILABLE" | "REQUEST_TIMEOUT" | "NOT_FOUND" | "INTERNAL_ERROR" | "HTTP_ERROR";

export interface ErrorResponse {
  request_id: string;
  error: { code: ApiErrorCode; message: string; retry_after_seconds?: number };
}

export interface HotspotQuery {
  product_id: string;
  province_code: string;
  date_from: string;
  date_to: string;
  limit: number;
}

export interface ApiClient {
  getMetadata(): Promise<MetadataResponse>;
  getSummary(request: SummaryRequest): Promise<SummaryResponse>;
  getHotspots(query: HotspotQuery): Promise<HotspotFeatureCollection>;
  getYearComparison(request: YearComparisonRequest): Promise<YearComparisonResponse>;
  chat(request: ChatRequest): Promise<ChatResponse>;
}
