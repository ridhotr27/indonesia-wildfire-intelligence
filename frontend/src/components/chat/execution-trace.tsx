import { ExternalIcon } from "@/components/ui/icons";
import type {
  ChatResponse,
  DataStatus,
  ExecutionTrace,
  ExecutionTraceDetails,
  ExecutionTraceStep,
  SourceAttribution,
} from "@/lib/api";
import type { A03ChatResponse } from "@/lib/api/a03-contract-proposal";
import { ProvinceAnalyticsEvidence } from "./province-analytics";

const routeLabels = { analytics: "Hotspot analytics", rag: "Documentation retrieval", combined: "Analytics and documentation", unsupported: "No supported operation" } as const;
const sourceLabels = { message: "your message", ui_context: "dashboard filters", absent: "not provided" } as const;
const operationLabels = {
  hotspot_summary_v1: "Monthly hotspot count",
  hotspot_trend_v1: "Monthly hotspot trend",
  hotspot_map_v1: "Bounded hotspot map",
  hotspot_year_comparison_v1: "Year-over-year hotspot comparison",
} as const;
const stepLabels: Record<ExecutionTraceStep["kind"], string> = {
  route_selection: "Request route selected",
  filter_resolution: "Filters resolved",
  analytics_query: "Approved analytics operation completed",
  vector_retrieval: "NASA documentation retrieved",
  local_generation: "Local documentation answer generated",
  citation_validation: "Citations validated",
  abstention: "Request abstained",
};
const words = (value: string) => value.replaceAll("_", " ");

export interface TraceDataContext {
  dataStatus: DataStatus;
  source: SourceAttribution;
}

function FilterDetails({ details }: { details: Extract<ExecutionTraceDetails, { kind: "filter_resolution" }> }) {
  return <dl className="trace-fields">
    <div><dt>Province codes</dt><dd>{details.province_codes.length ? details.province_codes.join(", ") : "Not provided"}</dd></div>
    <div><dt>Date range</dt><dd>{details.date_from && details.date_to ? `${details.date_from} to ${details.date_to}` : "Not provided"}</dd></div>
    <div><dt>Sources</dt><dd>Province: {sourceLabels[details.province_source]}; dates: {sourceLabels[details.date_from_source]} / {sourceLabels[details.date_to_source]}</dd></div>
    <div><dt>Outcome</dt><dd>{words(details.outcome)}</dd></div>
    {details.reason_codes.length > 0 && <div><dt>Needs attention</dt><dd>{details.reason_codes.map(words).join(", ")}</dd></div>}
  </dl>;
}

function operationSignature(details: Extract<ExecutionTraceDetails, { kind: "analytics_query" }>): string {
  if (details.operation_id === "hotspot_year_comparison_v1") return `${details.operation_id}(province_code="${details.parameters.province_code}", years=${JSON.stringify(details.parameters.years)})`;
  const provinces = JSON.stringify(details.parameters.province_codes);
  return `${details.operation_id}(province_codes=${provinces}, date_from="${details.parameters.date_from}", date_to="${details.parameters.date_to}")`;
}

function StepDetails({ details }: { details: ExecutionTraceDetails }) {
  switch (details.kind) {
    case "route_selection": return <p className="trace-detail">Route: {routeLabels[details.route]}</p>;
    case "filter_resolution": return <FilterDetails details={details} />;
    case "analytics_query": return <dl className="trace-fields"><div><dt>Approved operation</dt><dd>{operationLabels[details.operation_id]}</dd></div><div><dt>Display signature</dt><dd className="trace-signature">{operationSignature(details)}</dd></div><div><dt>Access</dt><dd>Read only</dd></div><div><dt>{details.operation_id === "hotspot_map_v1" ? "Bounded points in result" : details.operation_id === "hotspot_year_comparison_v1" ? "Years in result" : "Monthly periods in result"}</dt><dd>{details.returned_rows.toLocaleString("en-US")}</dd></div>{details.metric_name && details.operation_id !== "hotspot_year_comparison_v1" && <div><dt>Result</dt><dd>{details.metric_value === null || details.metric_value === undefined ? "Unavailable" : details.metric_value.toLocaleString("en-US")} {words(details.metric_name)}</dd></div>}</dl>;
    case "vector_retrieval": return <><dl className="trace-fields"><div><dt>Local index</dt><dd>{details.collection}</dd></div><div><dt>Embedding model</dt><dd>{details.embedding_model}</dd></div><div><dt>Retrieved</dt><dd>{details.returned_count} of top {details.top_k}</dd></div></dl>{details.items.length > 0 && <ol className="trace-links">{details.items.map((item) => <li key={item.chunk_id}><a href={item.url} target="_blank" rel="noopener noreferrer">{item.rank}. {item.title}<ExternalIcon className="h-3.5 w-3.5 shrink-0" /></a></li>)}</ol>}</>;
    case "local_generation": return <dl className="trace-fields"><div><dt>Provider</dt><dd>Local {details.provider}</dd></div><div><dt>Model</dt><dd>{details.model}</dd></div><div><dt>Inputs</dt><dd>{details.input_passage_count} passage{details.input_passage_count === 1 ? "" : "s"}; {details.model_calls} model call{details.model_calls === 1 ? "" : "s"}</dd></div></dl>;
    case "citation_validation": return <dl className="trace-fields"><div><dt>Citations</dt><dd>{details.accepted_count} accepted from {details.candidate_count} candidate{details.candidate_count === 1 ? "" : "s"}</dd></div><div><dt>Outcome</dt><dd>{details.outcome}</dd></div></dl>;
    case "abstention": return <p className="trace-detail">No operation ran: {words(details.reason_code)}.</p>;
  }
}

function TraceStep({ step }: { step: ExecutionTraceStep }) {
  return <li className="trace-step"><div className="trace-step-heading"><span aria-hidden="true">{step.sequence}</span><div><p>{stepLabels[step.kind]}</p><p>{words(step.status)}{step.duration_ms !== undefined && step.duration_ms !== null ? ` · ${step.duration_ms} ms` : ""}</p></div></div><StepDetails details={step.details} /></li>;
}

function verifiedOperationExplanation(operationId: Extract<ExecutionTraceDetails, { kind: "analytics_query" }>["operation_id"]): string {
  if (operationId === "hotspot_year_comparison_v1") return "FastAPI bound the validated province and years to one server-owned, parameterized, read-only ClickHouse aggregation grouped by year. No SQL came from you or the LLM.";
  if (operationId === "hotspot_map_v1") return "FastAPI bound the validated filters to server-owned, parameterized, read-only ClickHouse reads for bounded hotspot points and coverage. No SQL came from you or the LLM.";
  if (operationId === "hotspot_trend_v1") return "FastAPI bound the validated filters to server-owned, parameterized, read-only ClickHouse reads for UTC-month trends and coverage. No SQL came from you or the LLM.";
  return "FastAPI bound the validated filters to server-owned, parameterized, read-only ClickHouse reads for monthly counts and coverage. No SQL came from you or the LLM.";
}

function resultUnit(operationId: Extract<ExecutionTraceDetails, { kind: "analytics_query" }>["operation_id"], count: number): string {
  if (operationId === "hotspot_map_v1") return `bounded point${count === 1 ? "" : "s"}`;
  if (operationId === "hotspot_year_comparison_v1") return `year${count === 1 ? "" : "s"}`;
  return `monthly period${count === 1 ? "" : "s"}`;
}

function coverageDates(response: ChatResponse): string[] {
  const dates = [
    ...(response.chart?.series.flatMap((point) => point.coverage_issues.map((issue) => issue.date_utc)) ?? []),
    ...(response.year_comparison?.points.flatMap((point) => point.coverage_issues.map((issue) => issue.date_utc)) ?? []),
  ];
  return [...new Set(dates)];
}

function AnalyticsExplanation({ response, trace, dataContext }: { response: ChatResponse; trace: ExecutionTrace; dataContext: TraceDataContext }) {
  const analyticsStep = trace.steps.find((step) => step.kind === "analytics_query" && step.details.kind === "analytics_query");
  if (!analyticsStep || analyticsStep.details.kind !== "analytics_query") return null;
  if (dataContext.dataStatus !== dataContext.source.data_status) return null;

  const details = analyticsStep.details;
  const comparisonOperation = details.operation_id === "hotspot_year_comparison_v1";
  const filterStep = trace.steps.find((step) => step.kind === "filter_resolution" && step.details.kind === "filter_resolution");
  const filters = filterStep?.details.kind === "filter_resolution" ? filterStep.details : null;
  const metric = details.metric_name ? response.metrics?.find((item) => item.name === details.metric_name) : undefined;
  const issues = coverageDates(response);
  const isVerified = dataContext.dataStatus === "verified";
  const hasCompletedGeneration = trace.steps.some((step) => step.kind === "local_generation" && step.status === "complete");
  const metricText = comparisonOperation
    ? `${response.year_comparison?.points.length ?? 0} yearly values`
    : metric?.value === null || metric?.value === undefined ? "an unavailable numeric result" : `${metric.value.toLocaleString("en-US")} ${metric.unit}`;

  return <section className="trace-lineage" aria-labelledby={`trace-lineage-${response.request_id}`}>
    <div className="trace-lineage-heading">
      <p className="eyebrow">Data lineage</p>
      <h4 id={`trace-lineage-${response.request_id}`}>How the data became this answer</h4>
    </div>
    <p className="trace-lineage-overview">{isVerified
      ? "This explanation reports a fixed server-owned analytics path; it is not hidden model reasoning."
      : "This response used a synthetic repository for interface testing. It does not claim that a production database or NASA observation data was queried."}</p>
    <ol className="trace-flow" aria-label="Analytics answer construction">
      <li><strong>Request</strong><span>The request was classified as {trace.route === "combined" ? "combined analytics and documentation" : "hotspot analytics"}.</span></li>
      <li><strong>Filters</strong><span>{filters
        ? comparisonOperation
          ? `Province ${details.parameters.province_code} and years ${details.parameters.years.join(", ")} were validated from the request and dashboard context.`
          : `Province ${details.parameters.province_codes.join(", ")} came from ${sourceLabels[filters.province_source]}; ${details.parameters.date_from} to ${details.parameters.date_to} came from ${sourceLabels[filters.date_from_source]} and ${sourceLabels[filters.date_to_source]}.`
        : comparisonOperation
          ? `The validated scope was province ${details.parameters.province_code}, years ${details.parameters.years.join(", ")}.`
          : `The validated scope was province ${details.parameters.province_codes.join(", ")}, ${details.parameters.date_from} to ${details.parameters.date_to}.`}</span></li>
      <li><strong>Approved operation</strong><span><span className="trace-signature">{operationSignature(details)}</span> — {operationLabels[details.operation_id]}, read only.</span></li>
      <li><strong>{isVerified ? "ClickHouse" : "Synthetic repository"}</strong><span>{isVerified
        ? verifiedOperationExplanation(details.operation_id)
        : "FastAPI used the synthetic UI repository. No production analytics database ran, and these values are not NASA observations."}</span></li>
      <li><strong>Validated result</strong><span>{details.returned_rows.toLocaleString("en-US")} {resultUnit(details.operation_id, details.returned_rows)} in the normalized result; the exact result was {metricText}.{issues.length > 0
        ? metric?.value === null || metric?.value === undefined
          ? ` The response reports unavailable or unknown coverage for ${issues.join(", ")}; no numeric total is supportable.`
          : ` The observed subtotal was retained for available periods, and ${issues.join(", ")} was marked as unavailable or unknown coverage.`
        : metric?.value === 0
          ? " Zero is a numeric result; unavailable coverage would be reported separately. The backend checked coverage."
          : " The backend checked coverage; no broader completeness claim is added in the browser."}{analyticsStep.duration_ms !== undefined && analyticsStep.duration_ms !== null ? ` Recorded duration: ${analyticsStep.duration_ms} ms.` : ""}</span></li>
      <li><strong>Answer</strong><span>{trace.route === "analytics" && response.usage.llm_calls === 0 && !hasCompletedGeneration
        ? "The backend inserted this exact metric into the answer and any chart. No LLM generated or changed this number."
        : trace.route === "combined" && hasCompletedGeneration
          ? "The deterministic analytics metric was kept separate from the local documentation path. Retrieved NASA text and the local model could explain and cite documentation, but could not create, replace, or modify this metric."
          : "The validated analytics metric remains a deterministic tool result. No completed local documentation generation is claimed."}</span></li>
    </ol>
    <dl className="trace-lineage-source"><div><dt>Dataset/provider</dt><dd>{isVerified ? `${dataContext.source.provider} · ${dataContext.source.dataset_version}` : "Synthetic fixture · Not observation data"}</dd></div><div><dt>Metric</dt><dd>{metricText}</dd></div></dl>
  </section>;
}

export function ExecutionTraceDisclosure({ trace, response, dataContext }: { trace: ExecutionTrace | null | undefined; response?: ChatResponse; dataContext?: TraceDataContext }) {
  const provinceAnalytics = (response as A03ChatResponse | undefined)?.province_analytics;
  return <>
    {provinceAnalytics && <ProvinceAnalyticsEvidence analytics={provinceAnalytics} />}
    {trace && <details className="execution-trace"><summary><span>How this answer was generated</span><span className="trace-summary-meta">{routeLabels[trace.route]} · {trace.status}</span></summary><div className="trace-body"><p className="trace-intro">A request-local record of completed operations. It does not show hidden reasoning.</p>{response && dataContext && <AnalyticsExplanation response={response} trace={trace} dataContext={dataContext} />}<h4 className="trace-log-heading">Execution record</h4><ol className="trace-steps">{trace.steps.map((step) => <TraceStep key={step.sequence} step={step} />)}</ol></div></details>}
  </>;
}
