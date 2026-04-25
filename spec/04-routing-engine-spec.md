# Routing Engine Specification

## Scope

Defines flood-aware route calculation and ORS integration.

## Primary Modules

- `api/routing.py`: endpoint orchestration layer.
- `api/services/routing_service.py`: ORS + geometry processing.
- `api/services/polygon_selection_service.py`: nearest-polygon subset selection.

## Polygon Processing Flow

1. Load artifact JSON and extract valid `Polygon`/`MultiPolygon` features where `risk_level == "high"`.
2. Compute midpoint from start/end coordinates.
3. Select nearest polygons to midpoint up to `MAX_AVOID_POLYGONS`.
4. Merge with `unary_union`.
5. Simplify geometry using configured tolerance.
6. Normalize geometry output to GeoJSON mapping.

## ORS Request Contract

Request body includes:
- `coordinates`: `[[start.lon, start.lat], [end.lon, end.lat]]`
- optional `options.avoid_polygons`
- optional `radiuses` fallback array

Headers:
- `Content-Type: application/json`
- `Accept: application/geo+json, application/json`
- optional `Authorization: ORS_API_KEY` (sent only when key is non-empty)

## Fallback Strategy

- `2003` area error on avoid polygons:
1. retry with progressively fewer nearest polygons (`n -> n/2 -> ...`) while avoid polygons remain valid
2. if no valid reduced avoid geometry remains, drop avoid polygons and retry
3. emit warning(s) describing each fallback step

- `2010` unroutable point error:
1. set `radiuses=[ORS_FALLBACK_RADIUS_METERS, ORS_FALLBACK_RADIUS_METERS]`
2. retry route call
3. emit warning and `using_custom_radiuses=true`

- Other ORS failures propagate as HTTP `502`.

## Response Semantics

- `high_risk_polygon_count`: count after midpoint-based selection.
- `avoidance_polygon_count`: number of polygons used in final ORS request.
- `using_avoid_polygons`: final request included avoid polygons.
- `using_custom_radiuses`: fallback radius retry used.
- `warning`: optional concatenated fallback diagnostics.
