# System Overview Specification

## Purpose

Provide flood-risk artifacts from GloFAS and route requests that avoid high-risk flood polygons using OpenRouteService (ORS).

## Top-Level Components

- `api/app.py`: FastAPI app, static frontend serving, health, artifact endpoints.
- `api/routing.py`: routing endpoint wiring and request schema.
- `api/ingestion.py`: download/extract/process pipeline for flood GeoJSON generation.
- `api/services/artifact_service.py`: artifact existence and payload/file helpers.
- `api/services/routing_service.py`: ORS call logic and routing fallback orchestration.
- `api/services/polygon_selection_service.py`: nearest-polygon selection logic.
- `api/config.py`: centralized environment-driven settings.
- `api/scheduler.py`: recurring ingestion job runner.
- `frontend/`: static Leaflet frontend.

## Core Data Flow

1. Client requests frontend (`GET /`) or API endpoint.
2. For `/geojson/live` and `/route/avoid-flood-high-risk`, missing artifact triggers ingestion.
3. Ingestion creates `live_flood.geojson` from latest available GloFAS GRIB data.
4. Routing endpoint loads high-risk polygons, selects nearest subset, builds ORS `avoid_polygons`, and requests route.
5. Frontend fetches flood GeoJSON and route JSON and renders both on Leaflet map.

## External Dependencies

- Copernicus CDS via `cdsapi` for GloFAS forecast download.
- ORS Directions API for route computation.
- Leaflet + OpenStreetMap tile server in browser.

## Non-Functional Characteristics

- Stateless HTTP layer; artifact files persisted on disk (`data/`).
- Graceful routing fallbacks for common ORS failures (oversized avoid polygons, unroutable points).
- Modularized service layer for reusable business logic.
