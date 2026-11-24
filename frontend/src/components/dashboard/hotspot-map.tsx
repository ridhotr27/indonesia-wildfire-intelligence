"use client";

import * as maplibregl from "maplibre-gl";
import type { GeoJSONSource, Map as MapLibreMap, Marker } from "maplibre-gl";
import { useEffect, useRef, useState } from "react";
import type { DataStatus, HotspotFeatureCollection } from "@/lib/api";
import { StatusPill } from "@/components/ui/status-pill";

const mapStyle: maplibregl.StyleSpecification = {
  version: 8,
  sources: { osm: { type: "raster", tiles: ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"], tileSize: 256, attribution: "© OpenStreetMap contributors" } },
  layers: [{ id: "osm", type: "raster", source: "osm", paint: { "raster-saturation": -0.55, "raster-opacity": 0.78 } }],
};

function fitToHotspots(map: MapLibreMap, data: HotspotFeatureCollection) {
  if (data.features.length === 0) return;
  const longitudes = data.features.map((feature) => feature.geometry.coordinates[0]);
  const latitudes = data.features.map((feature) => feature.geometry.coordinates[1]);
  map.fitBounds(
    [
      [Math.min(...longitudes), Math.min(...latitudes)],
      [Math.max(...longitudes), Math.max(...latitudes)],
    ],
    { padding: 48, maxZoom: 8, duration: 0 },
  );
}

function renderDomMarkers(
  map: MapLibreMap,
  data: HotspotFeatureCollection,
  current: Marker[],
) {
  current.forEach((marker) => marker.remove());
  return data.features.map((feature) => {
    const element = document.createElement("span");
    element.className = "block h-3 w-3 rounded-full border-2 border-[#3b0a00] bg-[#ff4d00] shadow";
    element.setAttribute("aria-hidden", "true");
    return new maplibregl.Marker({ element })
      .setLngLat(feature.geometry.coordinates as [number, number])
      .addTo(map);
  });
}

export function HotspotMap({ data, dataStatus }: { data: HotspotFeatureCollection; dataStatus: DataStatus }) {
  const containerRef = useRef<HTMLDivElement>(null);
  const mapRef = useRef<MapLibreMap | null>(null);
  const markersRef = useRef<Marker[]>([]);
  const latestDataRef = useRef(data);
  const [mapReady, setMapReady] = useState(false);
  const [basemapError, setBasemapError] = useState(false);
  const [hotspotError, setHotspotError] = useState(false);

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return;
    try {
      maplibregl.setWorkerUrl("/maplibre-gl-worker.mjs");
      const map = new maplibregl.Map({ container: containerRef.current, style: mapStyle, center: [117, -2.5], zoom: 3.25, minZoom: 2.5, maxZoom: 12, attributionControl: {} });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "top-right");
      map.on("load", () => {
        try {
          map.addSource("hotspots", { type: "geojson", data: latestDataRef.current });
          map.addLayer({ id: "hotspot-halo", type: "circle", source: "hotspots", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 9, 10, 18], "circle-color": "#7f1d1d", "circle-opacity": 0.35, "circle-blur": 0.35 } });
          map.addLayer({ id: "hotspot-markers", type: "circle", source: "hotspots", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 5, 10, 10], "circle-color": "#ff4d00", "circle-stroke-color": "#3b0a00", "circle-stroke-width": 2, "circle-opacity": 1 } });
          map.addLayer({ id: "hotspot-cores", type: "circle", source: "hotspots", paint: { "circle-radius": ["interpolate", ["linear"], ["zoom"], 3, 1.75, 10, 3.5], "circle-color": "#fff200", "circle-opacity": 1 } });
          markersRef.current = renderDomMarkers(map, latestDataRef.current, markersRef.current);
          fitToHotspots(map, latestDataRef.current);
          setMapReady(true);
          setHotspotError(false);
        } catch {
          setHotspotError(true);
          return;
        }
        map.on("click", "hotspot-markers", (event) => {
          const feature = event.features?.[0];
          if (!feature || feature.geometry.type !== "Point") return;
          const properties = feature.properties as Record<string, string>;
          const content = document.createElement("div");
          const title = document.createElement("strong");
          title.textContent = dataStatus === "mock" ? "Synthetic hotspot detection" : "Satellite hotspot detection";
          const details = document.createElement("p");
          details.textContent = `${properties.acquired_at_utc ?? "Time unavailable"} · ${properties.province_code ?? "Unknown province"} · confidence ${properties.confidence_code ?? "unknown"}`;
          content.append(title, details);
          new maplibregl.Popup({ closeButton: false, offset: 10 }).setLngLat(feature.geometry.coordinates as [number, number]).setDOMContent(content).addTo(map);
        });
        map.on("mouseenter", "hotspot-markers", () => { map.getCanvas().style.cursor = "pointer"; });
        map.on("mouseleave", "hotspot-markers", () => { map.getCanvas().style.cursor = ""; });
      });
      map.on("error", (event) => {
        const sourceId = (event as typeof event & { sourceId?: string }).sourceId;
        const message = event.error?.message.toLowerCase() ?? "";
        if (sourceId === "hotspots" || message.includes("hotspot") || message.includes("geojson")) setHotspotError(true);
        else setBasemapError(true);
      });
      mapRef.current = map;
      return () => {
        markersRef.current.forEach((marker) => marker.remove());
        markersRef.current = [];
        map.remove();
        mapRef.current = null;
      };
    } catch { queueMicrotask(() => setBasemapError(true)); }
  }, [dataStatus]);

  useEffect(() => {
    latestDataRef.current = data;
    const source = mapRef.current?.getSource("hotspots") as GeoJSONSource | undefined;
    if (!source || !mapRef.current) return;
    let active = true;
    const reportHotspotError = (value: boolean) => {
      queueMicrotask(() => {
        if (active) setHotspotError(value);
      });
    };
    try {
      source.setData(data);
      markersRef.current = renderDomMarkers(mapRef.current, data, markersRef.current);
      fitToHotspots(mapRef.current, data);
      reportHotspotError(false);
    } catch {
      reportHotspotError(true);
    }
    return () => { active = false; };
  }, [data]);

  return (
    <section className="panel overflow-hidden" aria-labelledby="map-title">
      <div className="flex flex-wrap items-start justify-between gap-3 p-4 pb-3 lg:px-5 lg:pt-5"><div><p className="eyebrow">Spatial distribution</p><h2 id="map-title" className="mt-1 text-lg font-semibold">Indonesia hotspot map</h2></div><StatusPill tone={dataStatus === "mock" ? "amber" : "green"}><span className={`h-1.5 w-1.5 rounded-full ${dataStatus === "mock" ? "bg-amber-500" : "bg-forest-500"}`} /> {dataStatus === "mock" ? "Synthetic points" : "Verified points"}</StatusPill></div>
      <div className="relative h-[360px] bg-[#dfe8e2] lg:h-[386px]">
        <div ref={containerRef} className="absolute inset-0" aria-label={`Interactive map of ${dataStatus === "mock" ? "synthetic" : "verified"} hotspot detections`} />
        {!mapReady && !basemapError && !hotspotError && <div role="status" className="absolute left-3 top-3 z-10 rounded-lg bg-white/95 px-3 py-2 text-xs font-medium shadow">Loading hotspot map…</div>}
        {data.features.length === 0 && <div className="absolute inset-0 z-10 grid place-items-center bg-white/80 text-center backdrop-blur-sm"><div><p className="font-semibold">No map points returned</p><p className="mt-1 text-sm text-slate-500">Adjust the selected filters and try again.</p></div></div>}
        {(basemapError || hotspotError) && <div role="alert" className="absolute inset-x-3 top-3 z-20 space-y-1 rounded-lg border border-red-300 bg-red-50/95 p-3 text-xs text-red-900 shadow"><strong>Map loading issue</strong>{basemapError && <p>The basemap tiles could not be loaded. Hotspot markers may still be available.</p>}{hotspotError && <p>Hotspot markers could not be loaded. The summary remains available.</p>}</div>}
        {data.features.length > 0 && <div className="absolute bottom-7 left-3 z-10 rounded-lg border border-white/60 bg-white/90 px-3 py-2 text-[10px] shadow-sm backdrop-blur"><span className="relative mr-2 inline-block h-3 w-3 rounded-full border-2 border-[#3b0a00] bg-[#ff4d00] align-middle shadow"><span className="absolute inset-[3px] rounded-full bg-[#fff200]" /></span>{dataStatus === "mock" ? "Synthetic fixture hotspot" : "Satellite hotspot detection"}</div>}
      </div>
      <div className="flex flex-wrap items-center justify-between gap-2 px-4 py-3 text-[11px] text-slate-500 lg:px-5"><span>{data.metadata.returned} points shown{data.metadata.truncated ? " · Result truncated" : ""}</span><span>{data.metadata.source.dataset_version}</span></div>
    </section>
  );
}
