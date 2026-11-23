import type { SVGProps } from "react";

type IconProps = SVGProps<SVGSVGElement>;
const base = { width: 20, height: 20, viewBox: "0 0 24 24", fill: "none", stroke: "currentColor", strokeWidth: 1.8, strokeLinecap: "round" as const, strokeLinejoin: "round" as const, "aria-hidden": true };

export const FlameIcon = (props: IconProps) => <svg {...base} {...props}><path d="M12.8 2.4c.5 3-1.5 4.3-2.8 6.2-1.1 1.6-.8 3.3.4 4.3-.1-2.1 1.4-3.2 2.4-4.4 2 1.7 3.7 3.9 3.7 6.8A5.3 5.3 0 0 1 11.2 21a5.7 5.7 0 0 1-5.7-5.8c0-4.1 3.1-6.2 7.3-12.8Z"/><path d="M9.4 19.5c-1.2-2 .2-3.6 1.4-4.9.3 1.8 1.8 2.4 1.9 4.3"/></svg>;
export const MapIcon = (props: IconProps) => <svg {...base} {...props}><path d="m3 6 5-3 8 3 5-3v15l-5 3-8-3-5 3Z"/><path d="M8 3v15M16 6v15"/></svg>;
export const ChartIcon = (props: IconProps) => <svg {...base} {...props}><path d="M4 19V5M4 19h16"/><path d="m7 15 4-4 3 2 5-6"/></svg>;
export const SparkIcon = (props: IconProps) => <svg {...base} {...props}><path d="m12 3 1.2 4.3L17 9l-3.8 1.7L12 15l-1.2-4.3L7 9l3.8-1.7Z"/><path d="m18.5 14 .7 2.3 2.3.7-2.3.7-.7 2.3-.7-2.3-2.3-.7 2.3-.7Z"/></svg>;
export const SendIcon = (props: IconProps) => <svg {...base} {...props}><path d="m22 2-7 20-4-9-9-4Z"/><path d="M22 2 11 13"/></svg>;
export const ExternalIcon = (props: IconProps) => <svg {...base} {...props}><path d="M14 4h6v6M20 4 11 13"/><path d="M18 13v6a1 1 0 0 1-1 1H5a1 1 0 0 1-1-1V7a1 1 0 0 1 1-1h6"/></svg>;
export const InfoIcon = (props: IconProps) => <svg {...base} {...props}><circle cx="12" cy="12" r="9"/><path d="M12 11v5M12 8h.01"/></svg>;
export const RefreshIcon = (props: IconProps) => <svg {...base} {...props}><path d="M20 7h-5V2"/><path d="M20 7a8 8 0 1 0 1 7"/></svg>;
export const ChevronIcon = (props: IconProps) => <svg {...base} {...props}><path d="m9 18 6-6-6-6"/></svg>;
