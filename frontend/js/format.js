export function colorFor(feature) {
  const level = feature.properties?.risk_level;
  const colors = { high: "#d62828", medium: "#f77f00", low: "#2a9d8f" };
  return colors[level] || "#22577a";
}

export function floodTooltip(feature) {
  const p = feature.properties || {};
  return `Risk: ${p.risk_level ?? "n/a"} | Score: ${Number(p.risk_score ?? 0).toFixed(2)} | Discharge: ${Number(
    p.discharge ?? 0,
  ).toFixed(1)}`;
}

export function formatDistanceMeters(meters) {
  if (!Number.isFinite(meters)) {
    return "n/a";
  }
  return `${(meters / 1000).toFixed(1)} km`;
}

export function formatDurationSeconds(seconds) {
  if (!Number.isFinite(seconds)) {
    return "n/a";
  }
  const mins = Math.round(seconds / 60);
  return `${mins} min`;
}
