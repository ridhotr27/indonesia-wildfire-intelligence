import type { MetadataResponse, SummaryRequest } from "@/lib/api";

interface FilterBarProps {
  metadata: MetadataResponse;
  filters: SummaryRequest;
  onChange: (filters: SummaryRequest) => void;
  onApply: () => void;
  loading: boolean;
}

export function availableCoverageYears(coverage: MetadataResponse["coverage"]): number[] {
  const first = Number(coverage.date_min.slice(0, 4));
  const last = Number(coverage.date_max.slice(0, 4));
  return Array.from({ length: last - first + 1 }, (_, index) => first + index);
}

export function rangeForCoverageYear(coverage: MetadataResponse["coverage"], year: number) {
  const yearStart = `${year}-01-01`;
  const yearEnd = `${year}-12-31`;
  return {
    date_from: yearStart < coverage.date_min ? coverage.date_min : yearStart,
    date_to: yearEnd > coverage.date_max ? coverage.date_max : yearEnd,
  };
}

export function FilterBar({ metadata, filters, onChange, onApply, loading }: FilterBarProps) {
  const years = availableCoverageYears(metadata.coverage);
  const selectedYear = filters.date_from.slice(0, 4) === filters.date_to.slice(0, 4) ? filters.date_from.slice(0, 4) : "custom";
  return (
    <section className="panel p-4 lg:p-5" aria-labelledby="filters-title">
      <div className="mb-4 flex items-center justify-between gap-4">
        <div>
          <p className="eyebrow">Explore the archive</p>
          <h2 id="filters-title" className="mt-1 text-lg font-semibold">Analysis filters</h2>
        </div>
        <p className="hidden text-xs text-slate-500 md:block">Dates are inclusive · UTC</p>
      </div>
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-[1.25fr_1.1fr_.75fr_1fr_1fr_auto] lg:items-end">
        <label><span className="field-label">Province</span><select className="field" value={filters.province_codes[0]} onChange={(event) => onChange({ ...filters, province_codes: [event.target.value] })}>{metadata.provinces.map((province) => <option key={province.province_code} value={province.province_code}>{province.display_name}</option>)}</select></label>
        <label><span className="field-label">Satellite product</span><select className="field" value={filters.product_id} onChange={(event) => onChange({ ...filters, product_id: event.target.value })}>{metadata.products.map((product) => <option key={product.product_id} value={product.product_id}>{product.display_name}</option>)}</select></label>
        <label><span className="field-label">Year</span><select className="field" value={selectedYear} onChange={(event) => {
          if (event.target.value === "custom") return;
          onChange({ ...filters, ...rangeForCoverageYear(metadata.coverage, Number(event.target.value)) });
        }}><option value="custom">Custom</option>{years.map((year) => <option key={year} value={year}>{year}</option>)}</select></label>
        <label><span className="field-label">From</span><input className="field" type="date" min={metadata.coverage.date_min} max={metadata.coverage.date_max} value={filters.date_from} onChange={(event) => onChange({ ...filters, date_from: event.target.value })} /></label>
        <label><span className="field-label">To</span><input className="field" type="date" min={metadata.coverage.date_min} max={metadata.coverage.date_max} value={filters.date_to} onChange={(event) => onChange({ ...filters, date_to: event.target.value })} /></label>
        <button type="button" onClick={onApply} disabled={loading} className="h-10 rounded-lg bg-forest-700 px-5 text-sm font-semibold text-white shadow-sm transition hover:bg-forest-900 disabled:cursor-wait disabled:opacity-60 sm:col-span-2 lg:col-span-1">{loading ? "Updating…" : "Apply filters"}</button>
      </div>
    </section>
  );
}
