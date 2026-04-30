# HTTP API Specification

## Base Service

- Default local base URL: `http://127.0.0.1:8000`
- FastAPI app title: `Ingestion API`

## Endpoints

### `GET /health`

Returns service health status.

Response:

```json
{"status":"ok"}
```

### `GET /`

Returns frontend HTML (`frontend/index.html`) as `text/html`.

Error conditions:
- `404`: frontend file missing.

### `GET /geojson/live`

Query params:
- `source` (optional, default: `default`)

Behavior:
1. Ensures default artifact exists (`DEFAULT_ARTIFACT_PATH` or default location).
2. Triggers ingestion if missing.
3. Loads and returns GeoJSON payload as JSON.

Error conditions:
- `500`: ingestion output missing after ingestion attempt.
- `500`: invalid/unreadable GeoJSON payload.

### `POST /artifact`

Query params:
- `target` (required): path to artifact to return.
- `source` (optional, default: `default`)

Behavior:
1. If `target` exists and is a file, returns file directly.
2. Otherwise runs ingestion to generate it.
3. Returns resulting file.

Error conditions:
- `500`: ingestion output file missing after ingestion attempt.

### `POST /route/avoid-flood-high-risk`

Request body:

```json
{
  "start": {"lat": 46.0569, "lon": 14.5058},
  "end": {"lat": 45.8150, "lon": 15.9819},
  "source": "default",
  "artifact_path": "optional/path.geojson"
}
```

Validation:
- `lat` in `[-90, 90]`
- `lon` in `[-180, 180]`

Behavior:
1. Ensures artifact exists (uses `artifact_path` if provided; otherwise default artifact).
2. Loads all `risk_level == "high"` polygon geometries.
3. Selects up to `MAX_AVOID_POLYGONS` nearest polygons to midpoint between start/end.
4. Builds merged/simplified provider-compatible avoid geometry.
5. Calls configured routing provider (`ROUTING_PROVIDER`, default `openrouteservice`).
6. Applies fallback logic:
- avoid polygon area too large: retry with fewer polygons, then without avoid polygons.
- unroutable point: retry with custom routing radius values when the provider supports that option.
- route exceeds provider max distance: retry once without avoid polygons, then return `422` if still over limit.

OpenRouteService provider mappings:
- ORS error `2003`: avoid polygon area too large.
- ORS error `2010`: unroutable point.
- ORS error `2004`: route exceeds ORS max distance.

Response shape:

```json
{
  "artifact_path": "...",
  "high_risk_polygon_count": 123,
  "using_avoid_polygons": true,
  "using_custom_radiuses": false,
  "route": {"type": "FeatureCollection", "features": [...]},
  "warning": "optional warning text"
}
```

Error conditions:
- `500`: unsupported `ROUTING_PROVIDER`, missing provider credentials, or missing provider configuration.
- `500`: artifact parsing failures.
- `422`: route distance exceeds provider maximum distance.
- `502`: provider/network/response failures not resolved by fallback path.

## Static Asset Serving

- Mounted static path: `/static/frontend`
- Serves files from `frontend/`.
