import { act, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { mockHotspots } from "@/lib/api/mock-data";
import { HotspotMap } from "./hotspot-map";

const { setWorkerUrl } = vi.hoisted(() => ({ setWorkerUrl: vi.fn() }));
const handlers = new Map<string, (event?: unknown) => void>();
const addSource = vi.fn();
const addLayer = vi.fn();
const fitBounds = vi.fn();
const setData = vi.fn();
const markerSetLngLat = vi.fn();
const markerAddTo = vi.fn();
const markerRemove = vi.fn();

vi.mock("maplibre-gl", () => ({
  Map: class {
    addControl() {}
    addSource = addSource;
    addLayer = addLayer;
    fitBounds = fitBounds;
    getSource() { return { setData }; }
    getCanvas() { return { style: { cursor: "" } }; }
    on(event: string, layerOrHandler: string | ((event?: unknown) => void), maybeHandler?: (event?: unknown) => void) {
      const handler = typeof layerOrHandler === "function" ? layerOrHandler : maybeHandler;
      if (handler) handlers.set(typeof layerOrHandler === "string" ? `${event}:${layerOrHandler}` : event, handler);
    }
    remove() {}
  },
  NavigationControl: class {},
  Marker: class {
    setLngLat = markerSetLngLat.mockReturnThis();
    addTo = markerAddTo.mockReturnThis();
    remove = markerRemove;
  },
  Popup: class {},
  setWorkerUrl,
}));

beforeEach(() => {
  handlers.clear();
  addSource.mockClear();
  addLayer.mockClear();
  fitBounds.mockClear();
  setData.mockReset();
  setWorkerUrl.mockClear();
  markerSetLngLat.mockClear();
  markerAddTo.mockClear();
  markerRemove.mockClear();
});

describe("HotspotMap", () => {
  it("uses the latest props when data changes before MapLibre finishes loading", () => {
    const initial = structuredClone(mockHotspots);
    const updated = structuredClone(mockHotspots);
    updated.features = updated.features.slice(0, 1);
    updated.metadata.returned = 1;
    const view = render(<HotspotMap data={initial} dataStatus="mock" />);
    view.rerender(<HotspotMap data={updated} dataStatus="mock" />);

    act(() => handlers.get("load")?.());

    expect(addSource).toHaveBeenCalledWith("hotspots", expect.objectContaining({ data: updated }));
    expect(setWorkerUrl).toHaveBeenCalledWith("/maplibre-gl-worker.mjs");
    expect(addLayer).toHaveBeenCalledWith(expect.objectContaining({ id: "hotspot-markers", source: "hotspots", paint: expect.objectContaining({ "circle-color": "#ff4d00", "circle-stroke-color": "#3b0a00", "circle-stroke-width": 2 }) }));
    expect(addLayer).toHaveBeenCalledWith(expect.objectContaining({ id: "hotspot-cores", paint: expect.objectContaining({ "circle-color": "#fff200" }) }));
    expect(markerSetLngLat).toHaveBeenCalledWith([101.45, 0.52]);
    expect(markerAddTo).toHaveBeenCalled();
    expect(fitBounds).toHaveBeenCalledWith([[101.45, 0.52], [101.45, 0.52]], expect.objectContaining({ padding: 48, maxZoom: 8 }));
    expect(screen.getByText("Synthetic fixture hotspot")).toBeInTheDocument();
  });

  it("renders an explicit empty state without a hotspot legend", () => {
    const empty = structuredClone(mockHotspots);
    empty.features = [];
    empty.metadata.returned = 0;

    render(<HotspotMap data={empty} dataStatus="mock" />);
    act(() => handlers.get("load")?.());

    expect(screen.getByText("No map points returned")).toBeInTheDocument();
    expect(screen.queryByText("Synthetic fixture hotspot")).not.toBeInTheDocument();
    expect(fitBounds).not.toHaveBeenCalled();
  });

  it("surfaces basemap and hotspot source errors", () => {
    render(<HotspotMap data={mockHotspots} dataStatus="verified" />);
    act(() => handlers.get("load")?.());

    act(() => handlers.get("error")?.({ error: { message: "raster tile request failed" }, sourceId: "osm" }));
    expect(screen.getByText(/basemap tiles could not be loaded/i)).toBeInTheDocument();

    act(() => handlers.get("error")?.({ error: { message: "GeoJSON source failed" }, sourceId: "hotspots" }));
    expect(screen.getByText(/hotspot markers could not be loaded/i)).toBeInTheDocument();
  });

  it("clears a data update error after a later successful update", async () => {
    const initial = structuredClone(mockHotspots);
    const failing = structuredClone(mockHotspots);
    failing.metadata.returned = 1;
    const recovered = structuredClone(mockHotspots);
    recovered.metadata.returned = 2;
    const view = render(<HotspotMap data={initial} dataStatus="verified" />);
    act(() => handlers.get("load")?.());

    setData.mockImplementationOnce(() => { throw new Error("GeoJSON update failed"); });
    view.rerender(<HotspotMap data={failing} dataStatus="verified" />);
    expect(await screen.findByText(/hotspot markers could not be loaded/i)).toBeInTheDocument();

    view.rerender(<HotspotMap data={recovered} dataStatus="verified" />);
    await waitFor(() => {
      expect(screen.queryByText(/hotspot markers could not be loaded/i)).not.toBeInTheDocument();
    });
    expect(setData).toHaveBeenLastCalledWith(recovered);
  });
});
