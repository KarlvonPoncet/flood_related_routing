![Flood routing header](assets/readme/header.png)

# Ingestion API

## API Structure

- `api/app.py`: FastAPI entrypoint and HTTP route wiring.
- `api/routing.py`: routing endpoint wiring and request models.
- `api/services/artifact_service.py`: artifact existence/validation and GeoJSON loading.
- `api/services/routing_service.py`: ORS communication, flood polygon processing, and routing fallbacks.
- `api/ingestion.py`: ingestion pipeline (download, extract, transform, GeoJSON export).
- `api/config.py`: centralized runtime configuration from environment variables.

## CDS Credentials (`.cdsapirc`)

`api/ingestion.py` uses `cdsapi`, which requires a credentials file at:

- Linux/macOS: `~/.cdsapirc`
- Windows: `%USERPROFILE%\.cdsapirc`

Create the file with your Copernicus CDS API values:

```yaml
url: https://cds.climate.copernicus.eu/api
key: <your-uid>:<your-api-key>
```

Notes:

- Use credentials from your CDS account/API token page.
- Keep `.cdsapirc` out of version control and never commit real keys.
- If ingestion fails with authentication errors, verify the file path and key format first.

## License Activation (Copernicus EWDS / GloFAS)

Before using the ingestion API, accept the dataset licence once in your browser:

https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast?tab=download#manage-licences

1. Log in with the same account used for your API key.
2. Scroll to `Terms of use / Licences`.
3. Click `Accept` / `Agree`.

Without accepting, API requests fail with `400 Client Error: Not all the required licences have been accepted`.

## Run With Docker

### Docker Compose (recommended)

Create `.env` in the repo root and set at least:

```bash
ORS_API_KEY=<your_openrouteservice_key>
```

The routing provider is selected with `ROUTING_PROVIDER`. The default and currently implemented provider is:

```bash
ROUTING_PROVIDER=openrouteservice
```

To use a locally running ORS instance instead of the public ORS API:

```bash
ORS_USE_LOCAL=true
ORS_LOCAL_DIRECTIONS_URL=http://127.0.0.1:8080/ors/v2/directions/driving-car/geojson
```

Optional auth behavior override:

```bash
# default is false when ORS_USE_LOCAL=true, true otherwise
ORS_REQUIRE_API_KEY=false

# Timeout (seconds) for each ORS HTTP request from API container.
ORS_REQUEST_TIMEOUT_SECONDS=12
```

Routing endpoint selection logic:

- `ROUTING_PROVIDER=openrouteservice` uses the OpenRouteService provider implementation.
- If `ORS_USE_LOCAL=true` and `ORS_LOCAL_DIRECTIONS_URL` is set, requests go to local ORS.
- Otherwise requests go to `ORS_DIRECTIONS_URL` (remote/public ORS by default).
- `Authorization` header is sent only when `ORS_API_KEY` is non-empty.
- API key is required only when `ORS_REQUIRE_API_KEY=true`.

Start API:

```bash
docker compose up --build api
```

API is available at `http://127.0.0.1:8000/`.

`docker-compose.yml` mounts:

- `./data` to `/app/data` (artifacts persist on host)
- `${HOME}/.cdsapirc` to `/home/appuser/.cdsapirc:ro` (CDS credentials)
- Exports `CDSAPI_RC=/home/appuser/.cdsapirc` in the container

Start API + scheduler:

```bash
docker compose --profile scheduler up --build
```

Stop services:

```bash
docker compose down
```

### Docker CLI

Build image:

```bash
docker build -t flood-related-routing:latest .
```

Run API container:

```bash
docker run --rm -p 8000:8000 \
  -v "$(pwd)/data:/app/data" \
  -v "$HOME/.cdsapirc:/home/appuser/.cdsapirc:ro" \
  flood-related-routing:latest
```

Run scheduler container:

```bash
docker run --rm \
  -v "$(pwd)/data:/app/data" \
  -v "$HOME/.cdsapirc:/home/appuser/.cdsapirc:ro" \
  flood-related-routing:latest \
  python -m api.scheduler
```

## Run Locally (without Docker)

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
set -a; source .env; set +a
export CDSAPI_RC="$HOME/.cdsapirc"
uvicorn api.app:app --reload
```

Open `http://127.0.0.1:8000/` to view the map frontend.

Run the scheduler:

```bash
. .venv/bin/activate
python -m api.scheduler
```

Optional flags:

- `--interval-seconds 3600`: set custom frequency in seconds.
- `--skip-initial-run`: wait one full interval before the first run.

## Run Tests

```bash
. .venv/bin/activate
python -m pip install -r requirements-dev.txt
python -m pytest -q
```

Run live ORS integration tests (real network call, optional):

```bash
. .venv/bin/activate
set -a; source .env; set +a
RUN_LIVE_ORS_TESTS=1 python -m pytest -q -m live_ors
```

## Behavior

`POST /artifact?target=<path>&source=<source>`

- If `target` exists, the API returns that file.
- If `target` does not exist, the API runs ingestion and then returns the newly created file.

`GET /geojson/live`

- Returns `data/processed/live_flood.geojson`.
- If the file is missing, ingestion runs automatically and then returns GeoJSON.

`POST /route/avoid-flood-high-risk`

- Computes a driving route via OpenRouteService from `start` to `end`.
- Routing is called through the configured provider abstraction; OpenRouteService is the default provider.
- Extracts flood polygons with `risk_level == "high"` from the artifact and selects up to 200 nearest polygons to the midpoint between `start` and `end`.
- Passes the selected polygons as ORS `avoid_polygons`.
- If ORS rejects avoid area size (`code 2003`), the backend retries with progressively fewer nearest polygons before finally disabling avoidance.
- If the artifact does not exist, ingestion runs automatically first.
- Requires `ORS_API_KEY` in the API process environment.
  - Exception: when `ORS_USE_LOCAL=true`, API key is optional unless `ORS_REQUIRE_API_KEY=true`.

Example request:

```bash
curl -X POST "http://127.0.0.1:8000/route/avoid-flood-high-risk" \
  -H "Content-Type: application/json" \
  -d '{
    "start": { "lat": 46.0569, "lon": 14.5058 },
    "end": { "lat": 45.8150, "lon": 15.9819 }
  }'
```

For Docker Compose, pass the key when starting:

```bash
ORS_API_KEY=your_key_here docker compose up --build api
```

Current ingestion implementation is a placeholder in `api/ingestion.py`. Replace `ingest_file()` with your real ingestion flow.
