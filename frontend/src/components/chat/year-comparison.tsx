import type { YearComparisonResponse } from "@/lib/api";

export function YearComparisonEvidence({ comparison }: { comparison: YearComparisonResponse }) {
  return <section className="mt-4 overflow-hidden rounded-xl border border-slate-200" aria-label="Year-over-year hotspot comparison">
    <div className="bg-slate-50 px-3 py-2 text-xs font-semibold text-slate-700">Year-over-year detections</div>
    <dl className="grid divide-y divide-slate-100">
      {comparison.points.map((point) => <div key={point.year} className="grid grid-cols-[5rem_1fr] gap-3 px-3 py-2 text-sm">
        <dt className="font-medium">{point.year}</dt>
        <dd><span className="font-semibold">{point.count === null ? "Unavailable" : point.count.toLocaleString("en-US")}</span>{!point.is_complete && <span className="ml-2 text-xs text-amber-700">Partial coverage · missing dates unknown, not zero</span>}</dd>
      </div>)}
    </dl>
    <p className="border-t border-slate-100 px-3 py-2 text-[11px] text-slate-500">{comparison.caveat}</p>
  </section>;
}
