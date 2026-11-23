"use client";

import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from "recharts";
import type { DataStatus, SummaryResponse } from "@/lib/api";
import { StatusPill } from "@/components/ui/status-pill";

export function trendPeriodLabel(period: string, spansMultipleYears: boolean): string {
  return spansMultipleYears ? period : period.slice(5);
}

export function TrendChart({ summary, dataStatus }: { summary: SummaryResponse; dataStatus: DataStatus }) {
  const hasNumericPoints = summary.series.some((point) => point.count !== null);
  const spansMultipleYears = new Set(summary.series.map((point) => point.period.slice(0, 4))).size > 1;
  return (
    <section className="panel min-w-0 p-4 lg:p-5" aria-labelledby="trend-title">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div><p className="eyebrow">Temporal signal</p><h2 id="trend-title" className="mt-1 text-lg font-semibold">Hotspot detection trend</h2></div>
        <StatusPill tone={dataStatus === "mock" ? "amber" : "green"}><span className={`h-1.5 w-1.5 rounded-full ${dataStatus === "mock" ? "bg-amber-500" : "bg-forest-500"}`} /> {dataStatus === "mock" ? "Synthetic data" : "Verified data"}</StatusPill>
      </div>
      {!hasNumericPoints ? <div className="flex h-[290px] items-center justify-center text-center"><div><p className="font-semibold">No numeric result is available</p><p className="mt-1 text-sm text-slate-500">Coverage issues prevented a supported trend for this range.</p></div></div> : <div className="mt-5 h-[290px] w-full" role="img" aria-label="Area chart of monthly satellite hotspot detections"><ResponsiveContainer width="100%" height="100%"><AreaChart data={summary.series} margin={{ top: 8, right: 8, bottom: 0, left: -20 }}><defs><linearGradient id="trendFill" x1="0" y1="0" x2="0" y2="1"><stop offset="5%" stopColor="#287453" stopOpacity={0.3}/><stop offset="95%" stopColor="#287453" stopOpacity={0.02}/></linearGradient></defs><CartesianGrid stroke="#e7ece9" strokeDasharray="3 3" vertical={false}/><XAxis dataKey="period" axisLine={false} tickLine={false} tickFormatter={(value: string) => trendPeriodLabel(value, spansMultipleYears)} dy={8}/><YAxis axisLine={false} tickLine={false}/><Tooltip cursor={{ stroke: "#287453", strokeDasharray: "4 4" }} contentStyle={{ border: "1px solid #e2e8f0", borderRadius: 12, boxShadow: "0 8px 24px rgba(18,52,41,.10)", fontSize: 12 }} formatter={(value) => [value === null ? "Unavailable" : Number(value).toLocaleString(), "Detections"]}/><Area type="monotone" dataKey="count" connectNulls={false} stroke="#287453" strokeWidth={2.5} fill="url(#trendFill)" activeDot={{ r: 5, fill: "#ed6b35", stroke: "white", strokeWidth: 2 }}/></AreaChart></ResponsiveContainer></div>}
      <div className="mt-4 flex flex-wrap items-center justify-between gap-2 border-t border-slate-100 pt-3 text-[11px] text-slate-500"><span>Metric: satellite hotspot detections</span><span>{summary.source.dataset_version}</span></div>
    </section>
  );
}
