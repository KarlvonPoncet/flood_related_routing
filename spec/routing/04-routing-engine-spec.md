# Routing Engine Specification

## Scope

Defines flood-aware route calculation and routing provider integration.

## Primary Modules

- `api/routing.py`: endpoint orchestration layer.
- `api/services/routing_service.py`: provider abstraction, OpenRouteService provider implementation, retry orchestration, and geometry processing.
- `api/services/polygon_selection_service.py`: nearest-polygon subset selection.

## Polygon Processing Flow

1. Load artifact JSON and extract valid `Polygon`/`MultiPolygon` features where `risk_level == "high"`.
2. Compute midpoint from start/end coordinates.
3. Select nearest polygons to midpoint up to `MAX_AVOID_POLYGONS`.
4. Merge with `unary_union`.
5. Simplify geometry using configured tolerance.
6. Normalize geometry output to GeoJSON mapping.

## Provider Boundary

Routing providers implement the `RoutingProvider` protocol:
- `route(...)`: returns route output normalized to GeoJSON `FeatureCollection` where possible.
- `is_avoid_polygon_area_error(...)`: detects provider-specific avoid-area limit failures.
- `is_unroutable_point_error(...)`: detects provider-specific waypoint snapping failures.
- `is_distance_limit_error(...)`: detects provider-specific route distance limit failures.
- `extract_distance_limit_meters(...)`: extracts a numeric route limit for `422` diagnostics when available.

`ROUTING_PROVIDER=openrouteservice` selects the current default provider. Unsupported provider names fail fast with HTTP `500`.

## Provider Request Contract

The flood-aware route orchestration passes providers:
- `start` and `end` coordinates
- optional GeoJSON avoid geometry
- optional fallback radius values

Providers are responsible for translating those inputs into their own request format.

## OpenRouteService Request Mapping

Request body includes:
- `coordinates`: `[[start.lon, start.lat], [end.lon, end.lat]]`
- optional `options.avoid_polygons`
- optional `radiuses` fallback array

Headers:
- `Content-Type: application/json`
- `Accept: application/geo+json, application/json`
- optional `Authorization: ORS_API_KEY` (sent only when key is non-empty)

## Fallback Strategy

- avoid-area error:
1. retry with progressively fewer nearest polygons (`n -> n/2 -> ...`) while avoid polygons remain valid
2. if no valid reduced avoid geometry remains, drop avoid polygons and retry
3. emit warning(s) describing each fallback step

- unroutable point error:
1. set `radiuses=[ORS_FALLBACK_RADIUS_METERS, ORS_FALLBACK_RADIUS_METERS]`
2. retry route call
3. emit warning and `using_custom_radiuses=true`

- max distance error:
1. if avoid polygons are active, retry once without avoid polygons
2. if still over the distance limit, return HTTP `422` with guidance to choose closer points or increase the provider limit

- Other provider failures propagate as HTTP `502`.

## Response Semantics

- `high_risk_polygon_count`: count after midpoint-based selection.
- `avoidance_polygon_count`: number of polygons used in the final provider request.
- `using_avoid_polygons`: final request included avoid polygons.
- `using_custom_radiuses`: fallback radius retry used.
- `warning`: optional concatenated fallback diagnostics.
