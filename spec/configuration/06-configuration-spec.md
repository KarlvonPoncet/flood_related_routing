# Configuration Specification

## Scope

Centralized runtime settings via `api/config.py`.

## Model

`Settings` fields:
- path settings: `root_dir`, `default_artifact`, `frontend_index`, `raw_dir`, `zip_path`, `extract_dir`
- routing settings: `routing_provider`, `max_avoid_polygons`, `simplify_tolerance_degrees`
- request ingestion setting: `allow_request_ingestion`
- CORS setting: `cors_allow_origins`
- OpenRouteService settings: `ors_api_key`, `ors_use_local`, `ors_local_directions_url`, `ors_require_api_key`, `ors_directions_url`, `ors_fallback_radius_meters`
- custom routing graph settings: `custom_routing_graph_path`, `custom_routing_graph_metadata_path`, `custom_routing_osm_place`, `custom_routing_osm_network_type`, `custom_routing_simplify_graph`
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
- `ROUTING_PROVIDER`
- `CUSTOM_ROUTING_GRAPH_PATH`
- `CUSTOM_ROUTING_GRAPH_METADATA_PATH`
- `CUSTOM_ROUTING_OSM_PLACE`
- `CUSTOM_ROUTING_OSM_NETWORK_TYPE`
- `CUSTOM_ROUTING_SIMPLIFY_GRAPH`
- `MAX_AVOID_POLYGONS`
- `SIMPLIFY_TOLERANCE_DEGREES`
- `EU_MIN_LON`
- `EU_MAX_LON`
- `EU_MIN_LAT`
- `EU_MAX_LAT`
- `ALLOW_REQUEST_INGESTION`
- `CORS_ALLOW_ORIGINS`

## Parsing Rules

- Integer/float parsing validates type and raises `ValueError` with variable name on invalid values.
- Boolean parsing supports: `1/0`, `true/false`, `yes/no`, `on/off`.
- Path env values are `expanduser()`-normalized.
- Settings are cached with `lru_cache(maxsize=1)`.
- `ALLOW_REQUEST_INGESTION` defaults to `false` (production-safe mode); set to `true` for local/dev request-triggered rebuilds.
- `CORS_ALLOW_ORIGINS` is comma-separated and defaults to local development origins (`127.0.0.1`/`localhost` on common frontend ports). Use `*` only when explicitly configured.

## Routing Provider Resolution

`ROUTING_PROVIDER` defaults to `openrouteservice`. It is normalized to lowercase and selects the routing provider implementation used by the route endpoint. Unsupported providers fail at route time with HTTP `500`.

## OpenRouteService Endpoint Resolution

1. Resolve remote URL from `ORS_DIRECTIONS_URL` (default: public ORS endpoint).
2. Resolve local URL from `ORS_LOCAL_DIRECTIONS_URL`.
3. If `ORS_USE_LOCAL=true` and local URL exists, active `ors_directions_url` becomes local URL.
4. Otherwise active `ors_directions_url` is the remote URL.
5. `ors_require_api_key` defaults to `false` in local mode and `true` otherwise, unless explicitly set with `ORS_REQUIRE_API_KEY`.

## Custom Routing Graph Resolution

1. `CUSTOM_ROUTING_GRAPH_PATH` defaults to `data/raw/osm/custom-routing.graphml`.
2. `CUSTOM_ROUTING_GRAPH_METADATA_PATH` defaults to the graph path with `.metadata.json` suffix.
3. `CUSTOM_ROUTING_OSM_PLACE`, when set, tells graph ingestion to download by OSM place name.
4. If no place is configured, graph ingestion downloads by `EU_*` bounding box settings.
5. `CUSTOM_ROUTING_OSM_NETWORK_TYPE` defaults to `drive`.
6. `CUSTOM_ROUTING_SIMPLIFY_GRAPH` defaults to `true`.

## Reload Behavior

- `reload_settings()` clears the cached settings object (used by tests).
- Runtime code paths resolve settings when request/job work starts instead of relying on import-time copied module constants.
- `DEFAULT_ARTIFACT_PATH`, `MAX_AVOID_POLYGONS`, and `SIMPLIFY_TOLERANCE_DEGREES` changes take effect after `reload_settings()` without module re-imports.
