export function resolveApiUrl(pathname) {
  const params = new URLSearchParams(window.location.search);
  const apiBase = params.get("api_base");

  if (apiBase) {
    return new URL(pathname, apiBase).toString();
  }

  if (window.location.protocol === "file:") {
    return `http://127.0.0.1:8000${pathname}`;
  }

  return new URL(pathname, window.location.origin).toString();
}

export async function fetchLiveGeoJson() {
  const geojsonUrl = resolveApiUrl("/geojson/live");
  const response = await fetch(geojsonUrl);

  if (!response.ok) {
    throw new Error(`Failed to load map data from ${geojsonUrl}: HTTP ${response.status}`);
  }

  return response.json();
}

export async function fetchFloodAwareRoute(payload) {
  const routeUrl = resolveApiUrl("/route/avoid-flood-high-risk");
  const response = await fetch(routeUrl, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

  if (!response.ok) {
    const errText = await response.text();
    throw new Error(`HTTP ${response.status}: ${errText}`);
  }

  return response.json();
}
