"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, apiClient, type HotspotFeatureCollection, type MetadataResponse, type SummaryRequest, type SummaryResponse } from "@/lib/api";
import { ChatPanel } from "@/components/chat/chat-panel";
import { FilterBar } from "./filter-bar";
import { HotspotMap } from "./hotspot-map";
import { MetricCards } from "./metric-cards";
import { TrendChart } from "./trend-chart";
import { FlameIcon, InfoIcon, RefreshIcon } from "@/components/ui/icons";
import { StatusPill } from "@/components/ui/status-pill";

function DashboardSkeleton() {
  return <main className="mx-auto max-w-[1500px] space-y-4 px-4 py-6 lg:px-8"><div className="skeleton h-28"/><div className="skeleton h-32"/><div className="grid gap-4 sm:grid-cols-3">{[1,2,3].map((item) => <div key={item} className="skeleton h-28"/>)}</div><div className="grid gap-4 lg:grid-cols-2"><div className="skeleton h-[470px]"/><div className="skeleton h-[470px]"/></div></main>;
}

function errorMessage(caught: unknown): string {
  if (!(caught instanceof ApiError)) return caught instanceof Error ? caught.message : "The requested data could not be loaded.";
  if (caught.code === "RATE_LIMITED") return `Request limit reached. Try again${caught.retryAfterSeconds ? ` in ${caught.retryAfterSeconds} seconds` : " later"}.`;
  if (caught.code === "REQUEST_TIMEOUT") return "The request exceeded its processing deadline. Try a narrower range or retry later.";
  if (caught.code === "DEPENDENCY_UNAVAILABLE") return "A required data service is unavailable. No synthetic replacement was shown.";
  return caught.message;
}

const documentationOnlyFilters: SummaryRequest = {
  product_id: "MOCK_ONLY",
  province_codes: [],
  date_from: "2023-01-01",
  date_to: "2023-12-31",
  group_by: "month",
};

export function latestCalendarYearRange(coverage: MetadataResponse["coverage"]) {
  const latestYearStart = `${coverage.date_max.slice(0, 4)}-01-01`;
  return {
    date_from: latestYearStart < coverage.date_min ? coverage.date_min : latestYearStart,
    date_to: coverage.date_max,
  };
}

export function Dashboard() {
  const [metadata, setMetadata] = useState<MetadataResponse | null>(null);
  const [filters, setFilters] = useState<SummaryRequest | null>(null);
  const [appliedFilters, setAppliedFilters] = useState<SummaryRequest | null>(null);
  const [summary, setSummary] = useState<SummaryResponse | null>(null);
  const [hotspots, setHotspots] = useState<HotspotFeatureCollection | null>(null);
  const [initialLoading, setInitialLoading] = useState(true);
  const [updating, setUpdating] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const loadAnalysis = useCallback(async (nextFilters: SummaryRequest) => {
    setUpdating(true); setError(null);
    try {
      const [summaryResponse, mapResponse] = await Promise.all([
        apiClient.getSummary(nextFilters),
        apiClient.getHotspots({ product_id: nextFilters.product_id, province_code: nextFilters.province_codes[0], date_from: nextFilters.date_from, date_to: nextFilters.date_to, limit: 500 }),
      ]);
      setSummary(summaryResponse); setHotspots(mapResponse); setAppliedFilters(nextFilters);
    } catch (caught) {
      setError(errorMessage(caught));
    } finally { setUpdating(false); }
  }, []);

  const initialize = useCallback(async () => {
    setInitialLoading(true); setError(null);
    try {
      const response = await apiClient.getMetadata();
      if (!response.products[0] || !response.provinces[0]) throw new Error("No products or provinces are currently available.");
      const initialRange = latestCalendarYearRange(response.coverage);
      const initialFilters: SummaryRequest = { product_id: response.products[0].product_id, province_codes: [response.provinces[0].province_code], ...initialRange, group_by: "month" };
      setMetadata(response); setFilters(initialFilters);
      await loadAnalysis(initialFilters);
    } catch (caught) { setError(errorMessage(caught)); }
    finally { setInitialLoading(false); }
  }, [loadAnalysis]);

  useEffect(() => {
    let active = true;
    queueMicrotask(() => { if (active) void initialize(); });
    return () => { active = false; };
  }, [initialize]);

  if (initialLoading) return <DashboardSkeleton />;
  if (!metadata || !filters || !summary || !hotspots || !appliedFilters) return <main className="mx-auto min-h-screen max-w-4xl space-y-5 p-6"><div className="panel mx-auto max-w-md p-7 text-center"><div className="mx-auto grid h-12 w-12 place-items-center rounded-xl bg-red-50 text-red-700"><InfoIcon /></div><h1 className="mt-4 text-xl font-semibold">Dashboard unavailable</h1><p className="mt-2 text-sm leading-6 text-slate-500">{error ?? "The API returned an incomplete response."}</p><button onClick={() => void initialize()} className="mt-5 inline-flex items-center gap-2 rounded-lg bg-forest-700 px-4 py-2.5 text-sm font-semibold text-white"><RefreshIcon className="h-4 w-4"/> Try again</button></div><aside className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"><strong>Documentation-only mode.</strong> Analytics and map data remain unavailable, but the assistant below can retrieve approved NASA documentation from the local Qdrant index.</aside><ChatPanel filters={documentationOnlyFilters} provinceName="NASA FIRMS documentation"/></main>;

  const isMock = metadata.data_status === "mock";
  const provinceName = metadata.provinces.find((province) => province.province_code === appliedFilters.province_codes[0])?.display_name ?? appliedFilters.province_codes[0];
  return (
    <div className="min-h-screen">
      <header className="border-b border-black/[0.06] bg-white/80 backdrop-blur-xl"><div className="mx-auto flex max-w-[1500px] items-center justify-between gap-4 px-4 py-4 lg:px-8"><a href="#top" className="flex items-center gap-3"><span className="grid h-10 w-10 place-items-center rounded-xl bg-forest-700 text-white shadow-sm"><FlameIcon /></span><span><span className="block text-sm font-bold tracking-tight sm:text-base">Nusantara Firewatch</span><span className="hidden text-[10px] font-semibold uppercase tracking-[.16em] text-slate-500 sm:block">Indonesia intelligence agent</span></span></a><nav aria-label="Primary navigation" className="flex items-center gap-2 sm:gap-5"><a href="#overview" className="hidden text-sm font-medium text-slate-600 hover:text-forest-700 sm:block">Overview</a><a href="#assistant" className="hidden text-sm font-medium text-slate-600 hover:text-forest-700 sm:block">Ask agent</a><StatusPill tone={isMock ? "amber" : "green"}><span className={`h-1.5 w-1.5 rounded-full ${isMock ? "bg-amber-500" : "bg-forest-500"}`}/>{isMock ? "Demo mode" : "Verified API"}</StatusPill></nav></div></header>

      <main id="top" className="mx-auto max-w-[1500px] space-y-4 px-4 py-6 lg:space-y-5 lg:px-8 lg:py-8">
        <section className="relative overflow-hidden rounded-2xl bg-forest-900 px-5 py-6 text-white shadow-panel sm:px-7 lg:px-9 lg:py-8"><div className="absolute -right-12 -top-28 h-72 w-72 rounded-full border-[44px] border-white/[.035]"/><div className="relative max-w-3xl"><div className="flex items-center gap-2 text-[11px] font-bold uppercase tracking-[.2em] text-emerald-200"><span className="h-px w-7 bg-emerald-300"/>Historical intelligence workspace</div><h1 className="mt-3 text-2xl font-semibold tracking-tight sm:text-3xl lg:text-4xl">See Indonesia&apos;s hotspot patterns<br className="hidden sm:block"/> with evidence in view.</h1><p className="mt-3 max-w-2xl text-sm leading-6 text-emerald-50/75">Explore satellite-detected thermal anomalies through maps, trends, and a grounded conversational assistant. Designed for research—not emergency response.</p></div></section>

        {isMock && <aside className="flex items-start gap-3 rounded-xl border border-amber-300/70 bg-amber-50 px-4 py-3 text-amber-950"><InfoIcon className="mt-0.5 h-4 w-4 shrink-0"/><p className="text-xs leading-5"><strong>Synthetic demo dataset.</strong> Every count and point shown below is fabricated solely to exercise the interface and must not be interpreted as a NASA observation.</p></aside>}
        {error && <div role="alert" className="flex items-center justify-between gap-4 rounded-xl border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800"><span>{error}</span><button onClick={() => void loadAnalysis(filters)} className="shrink-0 font-semibold underline">Retry</button></div>}
        {!summary.is_complete && <aside role="status" className="rounded-xl border border-amber-300 bg-amber-50 px-4 py-3 text-sm text-amber-950"><strong>Incomplete satellite coverage.</strong> {summary.total === null ? "No numeric total is supportable for this range." : "The total includes available dates only."} {summary.coverage_issues.map((issue) => issue.date_utc).join(", ")} must not be interpreted as zero-detection days.</aside>}
        {summary.is_complete && summary.total === 0 && <aside role="status" className="rounded-xl border border-slate-200 bg-white px-4 py-3 text-sm text-slate-700"><strong>No detections returned.</strong> Coverage is complete for this selection; zero is a valid result.</aside>}

        <FilterBar metadata={metadata} filters={filters} onChange={setFilters} onApply={() => void loadAnalysis(filters)} loading={updating}/>
        <div id="overview" className={updating ? "pointer-events-none opacity-60 transition" : "transition"}><MetricCards summary={summary} provinceName={provinceName} dataStatus={metadata.data_status}/><div className="mt-4 grid gap-4 xl:grid-cols-[1.08fr_.92fr]"><HotspotMap data={hotspots} dataStatus={metadata.data_status}/><TrendChart summary={summary} dataStatus={metadata.data_status}/></div></div>
        <ChatPanel filters={appliedFilters} provinceName={provinceName} metadata={metadata}/>

        <section className="grid gap-4 rounded-2xl border border-slate-200 bg-white/70 p-5 text-sm sm:grid-cols-3 lg:p-6"><div><p className="eyebrow">Observation type</p><p className="mt-2 leading-6 text-slate-600">Satellite thermal anomaly detections—not confirmed wildfire incidents.</p></div><div><p className="eyebrow">Provenance</p><p className="mt-2 leading-6 text-slate-600">{metadata.source.provider}. Dataset: {metadata.source.dataset_version}.</p></div><div><p className="eyebrow">Known limits</p><p className="mt-2 leading-6 text-slate-600">Cloud, smoke, sensor timing, spatial resolution, and product methods can affect detections.</p></div></section>
      </main>
      <footer className="mt-4 border-t border-slate-200 bg-white/60"><div className="mx-auto flex max-w-[1500px] flex-col justify-between gap-2 px-4 py-5 text-xs text-slate-500 sm:flex-row lg:px-8"><span>Indonesia Wildfire Intelligence Agent v1.0</span><span>Exploratory research tool · Not an emergency warning service</span></div></footer>
    </div>
  );
}
