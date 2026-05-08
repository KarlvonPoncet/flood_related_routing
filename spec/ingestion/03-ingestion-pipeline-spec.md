# Ingestion Pipeline Specification

## Scope

Defines generation of flood-risk GeoJSON from GloFAS forecast data.

## Inputs

- CDS credentials via `.cdsapirc`/`CDSAPI_RC`.
- Runtime settings from `api/config.py`.

## Upstream Data Source

The ingestion service downloads forecast data from the Copernicus Climate Data Store / Early Warning Data Store through `cdsapi`.

Dataset:
- CDS/EWDS dataset id: `cems-glofas-forecast`
- Product family: GloFAS forecast
- System version: `operational`
- Hydrological model: `lisflood`
- Product type: `control_forecast`
- Variable: `river_discharge_in_the_last_24_hours`
- Forecast lead times: `24`, `48`, `72` hours
- Data format: `grib2`
- Download format: ZIP

Date selection:
- The pipeline tries the current UTC date first.
- If unavailable, it walks backward one day at a time for up to 7 UTC dates.
- The first successful forecast download is used.

Local raw storage:
- ZIP target defaults to `data/raw/glofas/glofas_slovenia.zip`.
- Extracted files default to `data/raw/glofas/extracted/`.
- Paths can be overridden with `GLOFAS_RAW_DIR`, `GLOFAS_ZIP_PATH`, and `GLOFAS_EXTRACT_DIR`.

Spatial scope:
- The downloaded GloFAS file is filtered during transform to configured Europe bounds.
- Bounds are controlled by `EU_MIN_LON`, `EU_MAX_LON`, `EU_MIN_LAT`, and `EU_MAX_LAT`.

## Outputs

- GeoJSON file at default artifact path or requested target.

## Pipeline Stages

### 1. Download (`download`)

- Attempts up to last 7 UTC dates.
- Requests dataset: `cems-glofas-forecast`.
- Variable: `river_discharge_in_the_last_24_hours`.
- Forecast lead times: `24`, `48`, `72`.
- Download format: ZIP containing GRIB2.

Failure:
- Raises `RuntimeError` if no successful date in 7-day window.

### 2. Extract (`extract_zip`)

- Clears extraction directory recursively (including nested folders/files).
- Validates every ZIP member path resolves under the extraction directory before extraction.
- Rejects unsafe ZIP archives (path traversal members such as `../...`).
- Extracts ZIP content only after validation passes.
- Selects first `.grib`/`.grib2` file recursively.

Failure:
- Raises `RuntimeError` if no GRIB file found.
- Raises `RuntimeError` when ZIP contains unsafe member paths.

### 3. Open GRIB (`open_glofas_grib`)

- Uses `xarray.open_dataset(..., engine="cfgrib")`.

Failure:
- Wraps missing cfgrib error with actionable install hint.

### 4. Transform (`process`)

Algorithm:
1. Resolve discharge variable (`river_discharge_in_the_last_24_hours` preferred; fallback first var).
2. Ensure latitude/longitude coordinates exist.
3. Reduce non-spatial dimensions by selecting index 0.
4. Sample grid every second cell.
5. Keep points within configured Europe bounds.
6. Skip NaN and values `< 500`.
7. Compute risk score `min(1.0, discharge/3000.0)` and level:
- `high` if `risk > 0.7`
- `medium` if `risk > 0.3`
- else `low`
8. Create polygon geometry by buffering point (`0.08` degrees).
9. Serialize as GeoJSON via GeoPandas.

Feature properties:
- `risk_score`, `risk_level`, `discharge`, `source`, `layer`, `timestamp`.

## Entry Points

- `run()`: full default pipeline to default artifact.
- `ingest_file(source, target)`: full pipeline to requested target path.
