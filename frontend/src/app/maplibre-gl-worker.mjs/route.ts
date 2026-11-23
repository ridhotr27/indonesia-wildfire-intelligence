import { readFile } from "node:fs/promises";
import { join } from "node:path";

export async function GET() {
  const workerPath = join(process.cwd(), "node_modules", "maplibre-gl", "dist", "maplibre-gl-worker.mjs");
  const workerSource = await readFile(workerPath);
  return new Response(workerSource, {
    headers: {
      "Cache-Control": "public, max-age=3600",
      "Content-Type": "text/javascript; charset=utf-8",
    },
  });
}
