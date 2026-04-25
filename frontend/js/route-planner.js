import { fetchFloodAwareRoute } from "./api.js";
import { formatDistanceMeters, formatDurationSeconds } from "./format.js";

export function createRoutePlanner({ mapController, statusEl, routeMetaEl, formEls }) {
  const { routeForm, startLatInput, startLonInput, endLatInput, endLonInput, pickStartBtn, pickEndBtn, clearRouteBtn } =
    formEls;

  let pickMode = null;

  startLatInput.value = "46.0569";
  startLonInput.value = "14.5058";
  endLatInput.value = "45.8150";
  endLonInput.value = "15.9819";

  function parseCoordinate(input) {
    const value = Number(input.value);
    if (!Number.isFinite(value)) {
      throw new Error("All coordinates must be valid numbers");
    }
    return value;
  }

  function updateStatusForPick() {
    if (pickMode === "start") {
      statusEl.textContent = "Click map to set start point";
    } else if (pickMode === "end") {
      statusEl.textContent = "Click map to set end point";
    }
  }

  mapController.onMapClick((event) => {
    if (!pickMode) {
      return;
    }

    const lat = Number(event.latlng.lat.toFixed(6));
    const lon = Number(event.latlng.lng.toFixed(6));

    if (pickMode === "start") {
      startLatInput.value = String(lat);
      startLonInput.value = String(lon);
      mapController.setMarker("start", lat, lon);
      statusEl.textContent = "Start point selected";
    } else {
      endLatInput.value = String(lat);
      endLonInput.value = String(lon);
      mapController.setMarker("end", lat, lon);
      statusEl.textContent = "End point selected";
    }

    pickMode = null;
  });

  pickStartBtn.addEventListener("click", () => {
    pickMode = "start";
    updateStatusForPick();
  });

  pickEndBtn.addEventListener("click", () => {
    pickMode = "end";
    updateStatusForPick();
  });

  clearRouteBtn.addEventListener("click", () => {
    mapController.clearRouteLayer();
    routeMetaEl.textContent = "";
  });

  routeForm.addEventListener("submit", async (event) => {
    event.preventDefault();

    try {
      const payload = {
        start: {
          lat: parseCoordinate(startLatInput),
          lon: parseCoordinate(startLonInput),
        },
        end: {
          lat: parseCoordinate(endLatInput),
          lon: parseCoordinate(endLonInput),
        },
      };

      mapController.setMarker("start", payload.start.lat, payload.start.lon);
      mapController.setMarker("end", payload.end.lat, payload.end.lon);

      statusEl.textContent = "Computing flood-aware route...";
      const data = await fetchFloodAwareRoute(payload);
      mapController.renderRouteLayer(data.route);

      const summary = data.route?.features?.[0]?.properties?.summary || {};
      const warningSuffix = data.warning ? ` | Warning: ${data.warning}` : "";
      const avoidanceCount = data.avoidance_polygon_count ?? 0;

      routeMetaEl.textContent = `Distance: ${formatDistanceMeters(summary.distance)} | Duration: ${formatDurationSeconds(
        summary.duration,
      )} | High-risk polygons: ${data.high_risk_polygon_count} | Avoidance polygons used: ${avoidanceCount} | Avoidance enabled: ${data.using_avoid_polygons} | Custom radiuses: ${data.using_custom_radiuses}${warningSuffix}`;
      statusEl.textContent = "Flood-aware route computed";
    } catch (error) {
      statusEl.textContent = `Route request failed: ${error.message}`;
    }
  });
}
