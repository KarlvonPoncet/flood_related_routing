# Testing Specification

## Framework

- `pytest`
- Marker config in `pytest.ini`

## Test Categories

### API Unit/Behavior Tests (`tests/test_api.py`)

Coverage includes:
- health endpoint
- frontend serving behavior
- artifact retrieval/build flow
- artifact path hardening (`..` traversal rejection and absolute-path allowlist enforcement)
- geojson live flow
- runtime settings reload behavior for `DEFAULT_ARTIFACT_PATH` in `GET /geojson/live`
- routing endpoint orchestration
- route `artifact_path` hardening with the same policy as `/artifact`
- request-ingestion gate behavior (`ALLOW_REQUEST_INGESTION=true|false`) for `/geojson/live`, `/artifact`, and route artifact resolution
- routing provider fallback behavior for avoid-area, unroutable-point, and distance-limit failures
- midpoint-nearest polygon selection integration (200 limit)
- route response-model validation for expected GeoJSON envelope shape
- route payload validation rejects FeatureCollections without a LineString route

### Artifact Service Unit Tests (`tests/test_artifact_service.py`)

Coverage includes:
- `503` behavior when request-triggered ingestion is disabled and artifact is missing
- per-artifact ingestion lock behavior that collapses concurrent rebuild attempts into a single ingestion run

### API Integration Tests (`tests/test_api.py`)

Coverage includes:
- Route endpoint + routing service integration for `/route/avoid-flood-high-risk` timeout handling
- `502` timeout diagnostics include provider host/port reachability hint
- ORS timeout value propagation from `ORS_REQUEST_TIMEOUT_SECONDS` into the OpenRouteService HTTP client call

### Ingestion Unit Tests (`tests/test_ingestion.py`)

Coverage includes:
- variable selection and dimension reduction helpers
- extract ZIP behavior
- extract ZIP nested cleanup and path traversal rejection behavior
- missing cfgrib error handling
- process edge cases (missing coords, NaNs, low values)
- runtime settings reload behavior for ingestion output path resolution

### Config Tests (`tests/test_config.py`)

Coverage includes:
- environment overrides
- invalid numeric env handling
- `ROUTING_PROVIDER` normalization
- unsupported routing provider rejection
- request-ingestion flag parsing/default behavior
- CORS allow-origin parsing/default behavior

### Polygon Selection Tests (`tests/test_polygon_selection_service.py`)

Coverage includes:
- limit behavior
- nearest-to-midpoint ordering behavior

### Routing Service Unit Tests (`tests/test_routing_service.py`)

Coverage includes:
- ORS error classification helpers
- mapping provider responses into structured exceptions (`AvoidAreaError`, `UnroutablePointError`, `DistanceLimitError`)
- fallback behavior through provider-neutral route call hooks

### Live ORS Integration (`tests/test_routing_live.py`)

- Marked `live_ors`
- Disabled unless `RUN_LIVE_ORS_TESTS=1`
- Requires `ORS_API_KEY`
- Executes real ORS call and validates non-empty route summary

## Expected Commands

Default local suite:

```bash
python -m pytest -q
```

Live ORS-only run:

```bash
RUN_LIVE_ORS_TESTS=1 python -m pytest -q -m live_ors
```
