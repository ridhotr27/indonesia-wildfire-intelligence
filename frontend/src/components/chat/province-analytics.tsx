import type { A03ProvinceAnalytics } from "@/lib/api/a03-contract-proposal";

export function ProvinceAnalyticsEvidence({ analytics }: { analytics: A03ProvinceAnalytics }) {
  const result = analytics.result;
  return (
    <section className="mt-4 overflow-hidden rounded-xl border border-slate-200" aria-label="Province hotspot comparison">
      <div className="flex flex-wrap justify-between gap-2 bg-slate-50 px-4 py-3">
        <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">{result.kind === "province_breakdown" ? "Province comparison" : "Province ranking"}</h3>
        <span className="text-xs text-slate-500">{result.date_from}–{result.date_to} UTC</span>
      </div>
      <div className="overflow-x-auto"><table className="w-full text-left text-sm">
        <thead><tr className="border-b border-slate-200 text-xs text-slate-500"><th className="px-4 py-2">Province</th>{result.kind === "province_ranking" && <th className="px-4 py-2">Rank</th>}<th className="px-4 py-2 text-right">Detections</th></tr></thead>
        <tbody>{result.rows.map((row) => <tr key={row.province_code} className="border-b border-slate-100 last:border-0"><th scope="row" className="px-4 py-2 font-medium">{row.province_name}</th>{"dense_rank" in row && <td className="px-4 py-2">{row.dense_rank}</td>}<td className="px-4 py-2 text-right tabular-nums">{row.count === null ? "Unavailable" : row.count.toLocaleString("en-US")}</td></tr>)}</tbody>
        {result.kind === "province_breakdown" && <tfoot><tr className="bg-forest-50 font-semibold"><th className="px-4 py-2">Combined total</th><td className="px-4 py-2 text-right tabular-nums">{result.total === null ? "Unavailable" : result.total.toLocaleString("en-US")}</td></tr></tfoot>}
      </table></div>
      <div className="space-y-1 border-t border-slate-200 px-4 py-3 text-xs text-slate-600">
        <p>{result.coverage_state === "complete" ? "Backend-checked coverage is complete for this range." : result.coverage_state === "partial" ? "Partial coverage: values use available observations only." : "Coverage is unavailable; no numeric result is asserted."}</p>
        <p>{result.not_assigned_to_exactly_one_province_count ?? "Unavailable"} observations were not assigned to exactly one province and are excluded.</p>
        <p>No LLM generated or changed these numbers.</p>
      </div>
    </section>
  );
}
