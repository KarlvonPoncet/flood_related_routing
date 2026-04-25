# Frontend Specification

## Scope

Static map UI for flood layer visualization and flood-aware routing.

## Assets

- HTML shell: `frontend/index.html`
- Styles: `frontend/styles.css`
- JS modules:
- `frontend/js/main.js`
- `frontend/js/api.js`
- `frontend/js/map-controller.js`
- `frontend/js/route-planner.js`
- `frontend/js/format.js`

## Runtime Dependencies

- Leaflet 1.9.4 from unpkg CDN.
- OSM tile server.

## API Integration

`frontend/js/api.js` resolves API base using:
1. `?api_base=<url>` query override
2. `http://127.0.0.1:8000` when loaded from `file:`
3. current origin otherwise

Calls:
- `GET /geojson/live`
- `POST /route/avoid-flood-high-risk`

## UI Features

- Flood polygons rendered as filled GeoJSON with tooltip metadata.
- Route planner form with start/end lat/lon.
- Map click mode for selecting start or end points.
- Route line rendering on successful route response.
- Summary panel includes:
- distance
- duration
- high-risk polygon count
- whether avoid polygons were used
- whether custom radiuses were used
- warning text (if present)

## Error Handling

- Tile load failures shown in status line.
- API failures surfaced directly in status line.
- Empty route feature set treated as client error.
