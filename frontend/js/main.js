import { fetchLiveGeoJson } from "./api.js";
import { createMapController } from "./map-controller.js";
import { createRoutePlanner } from "./route-planner.js";

const statusEl = document.getElementById("status");
const routeMetaEl = document.getElementById("route-meta");

const formEls = {
  routeForm: document.getElementById("route-form"),
  startLatInput: document.getElementById("start-lat"),
  startLonInput: document.getElementById("start-lon"),
  endLatInput: document.getElementById("end-lat"),
  endLonInput: document.getElementById("end-lon"),
  pickStartBtn: document.getElementById("pick-start"),
  pickEndBtn: document.getElementById("pick-end"),
  clearRouteBtn: document.getElementById("clear-route"),
};

const mapController = createMapController({
  mapId: "map",
  onTileError: () => {
    statusEl.textContent = "Base map tiles failed to load; polygons may still display";
  },
});

createRoutePlanner({
  mapController,
  statusEl,
  routeMetaEl,
  formEls,
});

async function loadLayer() {
  try {
    const data = await fetchLiveGeoJson();
    const count = mapController.renderFloodLayer(data);

    if (count === 0) {
      statusEl.textContent = "No risk zones found in dataset";
      return;
    }

    statusEl.textContent = `Loaded ${count} risk zones`;
  } catch (error) {
    statusEl.textContent = error.message;
  }
}

loadLayer();
