import { colorFor, floodTooltip } from "./format.js";

export function createMapController({ mapId, onTileError }) {
  const map = L.map(mapId, {
    zoomControl: true,
    minZoom: 2,
  }).setView([20, 0], 2);

  const tiles = L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 19,
    attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors',
  });

  tiles.on("tileerror", onTileError);
  tiles.addTo(map);

  let floodLayer = null;
  let routeLayer = null;
  let startMarker = null;
  let endMarker = null;

  function setMarker(kind, lat, lon) {
    const point = [lat, lon];
    if (kind === "start") {
      if (startMarker) {
        map.removeLayer(startMarker);
      }
      startMarker = L.circleMarker(point, {
        radius: 6,
        color: "#22577a",
        weight: 2,
        fillColor: "#fff",
        fillOpacity: 1,
      })
        .addTo(map)
        .bindTooltip("Start", { permanent: false });
      return;
    }

    if (endMarker) {
      map.removeLayer(endMarker);
    }
    endMarker = L.circleMarker(point, {
      radius: 6,
      color: "#3a5a40",
      weight: 2,
      fillColor: "#fff",
      fillOpacity: 1,
    })
      .addTo(map)
      .bindTooltip("End", { permanent: false });
  }

  function renderFloodLayer(data) {
    const features = data.features || [];
    if (floodLayer) {
      map.removeLayer(floodLayer);
    }

    floodLayer = L.geoJSON(data, {
      style: (feature) => {
        const color = colorFor(feature);
        return {
          color,
          weight: 1,
          fillColor: color,
          fillOpacity: 0.4,
        };
      },
      onEachFeature: (feature, layer) => {
        layer.bindTooltip(floodTooltip(feature), { sticky: true });
      },
    }).addTo(map);

    const bounds = floodLayer.getBounds();
    if (bounds.isValid()) {
      map.fitBounds(bounds.pad(0.2));
    }

    return features.length;
  }

  function renderRouteLayer(routeGeoJson) {
    const features = routeGeoJson?.features || [];
    if (features.length === 0) {
      throw new Error("Route API returned no features");
    }

    if (routeLayer) {
      map.removeLayer(routeLayer);
    }

    routeLayer = L.geoJSON(routeGeoJson, {
      style: {
        color: "#1d3557",
        weight: 5,
        opacity: 0.9,
      },
    }).addTo(map);

    const routeBounds = routeLayer.getBounds();
    if (routeBounds.isValid()) {
      map.fitBounds(routeBounds.pad(0.2));
    }
  }

  function clearRouteLayer() {
    if (routeLayer) {
      map.removeLayer(routeLayer);
      routeLayer = null;
    }
  }

  function onMapClick(handler) {
    map.on("click", handler);
  }

  return {
    setMarker,
    renderFloodLayer,
    renderRouteLayer,
    clearRouteLayer,
    onMapClick,
  };
}
