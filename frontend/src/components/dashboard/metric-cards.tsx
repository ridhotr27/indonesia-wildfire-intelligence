import type { DataStatus, SummaryResponse } from "@/lib/api";
import { ChartIcon, FlameIcon, MapIcon } from "@/components/ui/icons";

export function MetricCards({ summary, provinceName, dataStatus }: { summary: SummaryResponse; provinceName: string; dataStatus: DataStatus }) {
  const available = summary.series.filter((point): point is typeof point & { count: number } => point.count !== null);
  const peak = available.reduce((best, point) => point.count > best.count ? point : best, available[0] ?? { period: "—", count: 0, is_complete: false, coverage_issues: [] });
  const cards = [
    { label: "Hotspot detections", value: summary.total === null ? "Unavailable" : summary.total.toLocaleString("en-US"), detail: summary.is_complete ? (dataStatus === "mock" ? "Synthetic fixture count" : "Satellite detection count") : "Partial coverage", icon: FlameIcon, accent: "text-ember-600 bg-orange-50" },
    { label: "Peak period", value: available.length === 0 ? "Unavailable" : peak.period, detail: available.length === 0 ? "No covered numeric period" : `${peak.count.toLocaleString("en-US")} detections`, icon: ChartIcon, accent: "text-forest-600 bg-forest-50" },
    { label: "Selected region", value: provinceName, detail: "Province-level view", icon: MapIcon, accent: "text-sky-700 bg-sky-50" },
  ];
  return <section aria-label="Analysis summary" className="grid gap-3 sm:grid-cols-3">{cards.map(({ label, value, detail, icon: Icon, accent }) => <article key={label} className="panel flex items-start justify-between p-4 lg:p-5"><div className="min-w-0"><p className="text-xs font-medium text-slate-500">{label}</p><p className="mt-2 truncate text-xl font-semibold tracking-tight text-ink lg:text-2xl">{value}</p><p className="mt-1 text-xs text-slate-500">{detail}</p></div><span className={`ml-3 rounded-xl p-2.5 ${accent}`}><Icon className="h-5 w-5" /></span></article>)}</section>;
}
