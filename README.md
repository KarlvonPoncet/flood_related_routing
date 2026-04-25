# Ingestion API

## Setup

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
```

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

Before using the ingestion API, you must accept the dataset licence once in your browser.

Open:

https://ewds.climate.copernicus.eu/datasets/cems-glofas-forecast?tab=download#manage-licences

1. Log in with the same account used for your API key.
2. Scroll to `Terms of use / Licences`.
3. Click `Accept` / `Agree`.

Important:

- This is required once per dataset.
- Without accepting the licence, all API requests fail with:
  `400 Client Error: Not all the required licences have been accepted`
- After accepting:
  - ingestion works
  - scheduler works
  - no further action needed

### Verify

Run:

```bash
python -m api.ingestion
```

If successful, you will see:

`Downloaded GloFAS forecast for YYYY-MM-DD`

## Run

```bash
. .venv/bin/activate
uvicorn api.app:app --reload
```

Open `http://127.0.0.1:8000/` to view the map frontend.

## Hourly Scheduler

Run ingestion every hour to keep `data/processed/live_flood.geojson` up to date:

```bash
. .venv/bin/activate
python -m api.scheduler
```

Optional flags:

- `--interval-seconds 3600`: set custom frequency in seconds.
- `--skip-initial-run`: wait one full interval before the first run.

## Behavior

`POST /artifact?target=<path>&source=<source>`

- If `target` exists, the API returns that file.
- If `target` does not exist, the API runs ingestion and then returns the newly created file.

`GET /geojson/live`

- Returns `data/processed/live_flood.geojson`.
- If the file is missing, ingestion runs automatically and then returns GeoJSON.

Current ingestion implementation is a placeholder in `api/ingestion.py`. Replace `ingest_file()` with your real ingestion flow.
