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
2. If missing and `ALLOW_REQUEST_INGESTION=true`, ingestion runs in-request.
3. If missing and `ALLOW_REQUEST_INGESTION=false`, request fails fast.
4. Loads and returns GeoJSON payload as JSON.

Error conditions:
- `503`: artifact missing while request-triggered ingestion is disabled.
- `500`: ingestion output missing after ingestion attempt.
- `500`: invalid/unreadable GeoJSON payload.

### `POST /artifact`

Query params:
- `target` (required): path to artifact to return.
- `source` (optional, default: `default`)

Path policy:
- `target` is resolved through server-side path policy before any file read/write.
- Allowed roots are restricted to project artifact locations (`data/processed/`) and local scratch directories (`tmp/`, system temp).
- Parent traversal segments (`..`) are rejected.
- Absolute paths outside allowed roots are rejected.

Behavior:
1. If `target` exists and is a file, returns file directly.
2. If `target` is missing and `ALLOW_REQUEST_INGESTION=true`, runs ingestion to generate it.
3. If `target` is missing and `ALLOW_REQUEST_INGESTION=false`, request fails fast.
4. Returns resulting file.

Error conditions:
- `400`: unsafe path (`..`) or absolute path outside allowed roots.
- `503`: target file missing while request-triggered ingestion is disabled.
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
2. If artifact is missing and `ALLOW_REQUEST_INGESTION=true`, ingestion runs in-request.
3. If artifact is missing and `ALLOW_REQUEST_INGESTION=false`, request fails fast.
4. Loads all `risk_level == "high"` polygon geometries.
5. Selects up to `MAX_AVOID_POLYGONS` nearest polygons to midpoint between start/end.
6. Builds merged/simplified provider-compatible avoid geometry.
7. Calls configured routing provider (`ROUTING_PROVIDER`, default `openrouteservice`).
8. Applies fallback logic:
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
- `400`: `artifact_path` fails the same path policy as `/artifact` (`..` traversal or absolute path outside allowed roots).
- `503`: artifact missing while request-triggered ingestion is disabled.
- `500`: unsupported `ROUTING_PROVIDER`, missing provider credentials, or missing provider configuration.
- `500`: artifact parsing failures.
- `422`: route distance exceeds provider maximum distance.
- `502`: provider/network/response failures not resolved by fallback path.

## Static Asset Serving

- Mounted static path: `/static/frontend`
- Serves files from `frontend/`.

## CORS

- Browser CORS origins come from `CORS_ALLOW_ORIGINS`.
- Default configuration is local-development origins (not wildcard).
- To allow all origins, set `CORS_ALLOW_ORIGINS=*` explicitly.
