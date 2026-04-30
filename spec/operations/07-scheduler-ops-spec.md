# Scheduler and Operations Specification

## Scheduler

Module: `api/scheduler.py`

### CLI Interface

- `--interval-seconds` (default `3600`, must be > 0)
- `--skip-initial-run` (bool)

### Runtime Behavior

1. Starts loop with next run immediately or after one interval.
2. Sleeps in chunks up to 30 seconds until next run timestamp.
3. Executes ingestion (`api.ingestion.run`).
4. Logs success or exception.
5. Computes next run timestamp with drift protection.

### Failure Model

- Individual run failures are logged; scheduler loop continues.
- Invalid interval raises `ValueError`.

## Container/Deployment Notes

- `docker-compose.yml` provides `api` and optional `scheduler` profile service.
- Data volume mounted to `/app/data`.
- `.cdsapirc` mounted read-only and exposed as `CDSAPI_RC`.
- `.env` used for routing provider configuration.
- `ROUTING_PROVIDER=openrouteservice` selects the current default provider.
- Local OpenRouteService can be activated with:
  - `ORS_USE_LOCAL=true`
  - `ORS_LOCAL_DIRECTIONS_URL=<local-directions-endpoint>`
  - optional `ORS_REQUIRE_API_KEY=false` for unauthenticated local gateways.
- Custom routing graph ingestion can be run with:
  - `python -m api.osm_graph_ingestion`
  - optional `CUSTOM_ROUTING_OSM_PLACE=<place-name>`
  - optional `CUSTOM_ROUTING_GRAPH_PATH=<graphml-output>`
