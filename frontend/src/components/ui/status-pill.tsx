import type { ReactNode } from "react";

export function StatusPill({ children, tone = "green" }: { children: ReactNode; tone?: "green" | "amber" | "slate" }) {
  const styles = tone === "amber" ? "border-amber-300 bg-amber-50 text-amber-800" : tone === "slate" ? "border-slate-200 bg-slate-50 text-slate-600" : "border-forest-500/20 bg-forest-50 text-forest-700";
  return <span className={`inline-flex items-center gap-1.5 rounded-full border px-2.5 py-1 text-[11px] font-bold uppercase tracking-wider ${styles}`}>{children}</span>;
}
