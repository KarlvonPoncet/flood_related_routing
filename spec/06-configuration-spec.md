# Configuration Specification

## Scope

Centralized runtime settings via `api/config.py`.

## Model

`Settings` fields:
- path settings: `root_dir`, `default_artifact`, `frontend_index`, `raw_dir`, `zip_path`, `extract_dir`
- ORS settings: `ors_api_key`, `ors_use_local`, `ors_local_directions_url`, `ors_require_api_key`, `ors_directions_url`, `ors_fallback_radius_meters`
- routing tuning: `max_avoid_polygons`, `simplify_tolerance_degrees`
- ingestion geographic bounds: `eu_min_lon`, `eu_max_lon`, `eu_min_lat`, `eu_max_lat`

## Environment Variables

Supported overrides:
- `APP_ROOT_DIR`
- `DEFAULT_ARTIFACT_PATH`
- `FRONTEND_INDEX_PATH`
- `GLOFAS_RAW_DIR`
- `GLOFAS_ZIP_PATH`
- `GLOFAS_EXTRACT_DIR`
- `ORS_API_KEY`
- `ORS_USE_LOCAL`
- `ORS_LOCAL_DIRECTIONS_URL`
- `ORS_REQUIRE_API_KEY`
- `ORS_DIRECTIONS_URL`
- `ORS_FALLBACK_RADIUS_METERS`
- `MAX_AVOID_POLYGONS`
- `SIMPLIFY_TOLERANCE_DEGREES`
- `EU_MIN_LON`
- `EU_MAX_LON`
- `EU_MIN_LAT`
- `EU_MAX_LAT`

## Parsing Rules

- Integer/float parsing validates type and raises `ValueError` with variable name on invalid values.
- Boolean parsing supports: `1/0`, `true/false`, `yes/no`, `on/off`.
- Path env values are `expanduser()`-normalized.
- Settings are cached with `lru_cache(maxsize=1)`.

## ORS Endpoint Resolution Rules

1. Resolve remote URL from `ORS_DIRECTIONS_URL` (default: public ORS endpoint).
2. Resolve local URL from `ORS_LOCAL_DIRECTIONS_URL`.
3. If `ORS_USE_LOCAL=true` and local URL exists, active `ors_directions_url` becomes local URL.
4. Otherwise active `ors_directions_url` is the remote URL.
5. `ors_require_api_key` defaults to `false` in local mode and `true` otherwise, unless explicitly set with `ORS_REQUIRE_API_KEY`.

## Reload Behavior

- `reload_settings()` clears the cached settings object (used by tests).
