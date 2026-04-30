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
- geojson live flow
- routing endpoint orchestration
- routing provider fallback behavior for avoid-area, unroutable-point, and distance-limit failures
- midpoint-nearest polygon selection integration (200 limit)

### API Integration Tests (`tests/test_api.py`)

Coverage includes:
- Route endpoint + routing service integration for `/route/avoid-flood-high-risk` timeout handling
- `502` timeout diagnostics include provider host/port reachability hint
- ORS timeout value propagation from `ORS_REQUEST_TIMEOUT_SECONDS` into the OpenRouteService HTTP client call

### Ingestion Unit Tests (`tests/test_ingestion.py`)

Coverage includes:
- variable selection and dimension reduction helpers
- extract ZIP behavior
- missing cfgrib error handling
- process edge cases (missing coords, NaNs, low values)

### Config Tests (`tests/test_config.py`)

Coverage includes:
- environment overrides
- invalid numeric env handling
- `ROUTING_PROVIDER` normalization
- unsupported routing provider rejection

### Polygon Selection Tests (`tests/test_polygon_selection_service.py`)

Coverage includes:
- limit behavior
- nearest-to-midpoint ordering behavior

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
