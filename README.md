# Ingestion API

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

Start API:

```bash
docker compose up --build api
```

API is available at `http://127.0.0.1:8000/`.

`docker-compose.yml` mounts:

- `./data` to `/app/data` (artifacts persist on host)
- `${HOME}/.cdsapirc` to `/home/appuser/.cdsapirc:ro` (CDS credentials)

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

## Behavior

`POST /artifact?target=<path>&source=<source>`

- If `target` exists, the API returns that file.
- If `target` does not exist, the API runs ingestion and then returns the newly created file.

`GET /geojson/live`

- Returns `data/processed/live_flood.geojson`.
- If the file is missing, ingestion runs automatically and then returns GeoJSON.

`POST /route/avoid-flood-high-risk`

- Computes a driving route via OpenRouteService from `start` to `end`.
- Extracts flood polygons with `risk_level == "high"` from the artifact and passes them as ORS `avoid_polygons`.
- If the artifact does not exist, ingestion runs automatically first.
- Requires `ORS_API_KEY` in the API process environment.

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
