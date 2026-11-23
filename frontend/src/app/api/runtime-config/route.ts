import type { ApiMode } from "@/lib/api/types";
import { publicApiUrl } from "@/lib/api/runtime-config";

export const dynamic = "force-dynamic";

export function GET() {
  const mode: ApiMode = process.env.WILDFIRE_FRONTEND_API_MODE === "mock" ? "mock" : "real";
  const apiBaseUrl = mode === "real" ? publicApiUrl(process.env.WILDFIRE_PUBLIC_API_BASE_URL ?? "http://localhost:8000/api/v1") : null;
  return Response.json({ mode, apiBaseUrl }, { headers: { "Cache-Control": "no-store" } });
}
