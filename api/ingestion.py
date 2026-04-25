from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path
import zipfile

import cdsapi
import geopandas as gpd
import numpy as np
import xarray as xr
from shapely.geometry import Point


ROOT_DIR = Path(__file__).resolve().parent.parent
OUT = ROOT_DIR / "data/processed/live_flood.geojson"

RAW_DIR = ROOT_DIR / "data/raw/glofas"
ZIP_PATH = RAW_DIR / "glofas_slovenia.zip"
EXTRACT_DIR = RAW_DIR / "extracted"
EU_MIN_LON = -25.0
EU_MAX_LON = 45.0
EU_MIN_LAT = 34.0
EU_MAX_LAT = 72.0

OUT.parent.mkdir(parents=True, exist_ok=True)
RAW_DIR.mkdir(parents=True, exist_ok=True)
EXTRACT_DIR.mkdir(parents=True, exist_ok=True)


def download(target_path: Path = ZIP_PATH) -> Path:
    client = cdsapi.Client()

    # Try today, yesterday, day before...
    for offset in range(0, 7):
        date = datetime.now(timezone.utc) - timedelta(days=offset)

        request = {
            "system_version": ["operational"],
            "hydrological_model": ["lisflood"],
            "product_type": ["control_forecast"],
            "variable": "river_discharge_in_the_last_24_hours",
            "year": [str(date.year)],
            "month": [f"{date.month:02d}"],
            "day": [f"{date.day:02d}"],
            "leadtime_hour": ["24", "48", "72"],
            "data_format": "grib2",
            "download_format": "zip",
        }

        try:
            print(f"Trying GloFAS date: {date.date()}")
            client.retrieve(
                "cems-glofas-forecast",
                request,
                str(target_path),
            )
            print(f"Downloaded GloFAS forecast for {date.date()}")
            return target_path

        except Exception as e:
            print(f"Failed for {date.date()}: {e}")

    raise RuntimeError("No valid GloFAS forecast found in the last 7 days.")


def extract_zip(zip_path: Path = ZIP_PATH) -> Path:
    for old in EXTRACT_DIR.glob("*"):
        old.unlink()

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(EXTRACT_DIR)

    grib_files = list(EXTRACT_DIR.rglob("*.grib")) + list(EXTRACT_DIR.rglob("*.grib2"))

    if not grib_files:
        raise RuntimeError("No GRIB files found in downloaded ZIP.")

    return grib_files[0]


def open_glofas_grib(grib_path: Path) -> xr.Dataset:
    try:
        return xr.open_dataset(
            grib_path,
            engine="cfgrib",
            backend_kwargs={
                "indexpath": "",
            },
        )
    except ValueError as exc:
        # xarray raises ValueError("unrecognized engine 'cfgrib' ...") when cfgrib is missing.
        if "unrecognized engine 'cfgrib'" in str(exc):
            raise RuntimeError(
                "Missing GRIB backend. Install cfgrib in the active environment: "
                "python -m pip install cfgrib"
            ) from exc
        raise


def _get_main_variable(ds: xr.Dataset) -> str:
    if "river_discharge_in_the_last_24_hours" in ds.data_vars:
        return "river_discharge_in_the_last_24_hours"

    # GloFAS GRIB often has shortened variable names
    data_vars = list(ds.data_vars)

    if not data_vars:
        raise RuntimeError("No data variables found in GloFAS file.")

    return data_vars[0]


def _to_2d_grid(data_array: xr.DataArray) -> np.ndarray:
    reduced = data_array

    for dim in list(reduced.dims):
        if dim not in ("latitude", "longitude"):
            reduced = reduced.isel({dim: 0})

    return reduced.values


def _is_in_europe(lat: float, lon: float) -> bool:
    return EU_MIN_LAT <= lat <= EU_MAX_LAT and EU_MIN_LON <= lon <= EU_MAX_LON


def process(grib_path: Path, out_path: Path = OUT) -> Path:
    ds = open_glofas_grib(grib_path)

    var_name = _get_main_variable(ds)

    if "latitude" not in ds or "longitude" not in ds:
        raise RuntimeError("Dataset has no latitude/longitude coordinates.")

    lats = ds.latitude.values
    lons = ds.longitude.values
    discharge = _to_2d_grid(ds[var_name])

    features: list[dict] = []
    timestamp = datetime.now(timezone.utc).isoformat()

    for i in range(0, len(lats), 2):
        for j in range(0, len(lons), 2):
            lat = float(lats[i])
            lon = float(lons[j])

            if not _is_in_europe(lat=lat, lon=lon):
                continue

            val = discharge[i][j]

            if np.isnan(val):
                continue

            val = float(val)

            if val < 500:
                continue

            risk = min(1.0, val / 3000.0)

            if risk > 0.7:
                level = "high"
            elif risk > 0.3:
                level = "medium"
            else:
                level = "low"

            geom = Point(lon, lat).buffer(0.08)

            features.append(
                {
                    "type": "Feature",
                    "properties": {
                        "risk_score": risk,
                        "risk_level": level,
                        "discharge": val,
                        "source": "glofas",
                        "layer": "forecast",
                        "timestamp": timestamp,
                    },
                    "geometry": geom.__geo_interface__,
                }
            )

    gdf = gpd.GeoDataFrame.from_features(features, crs="EPSG:4326")
    gdf.to_file(out_path, driver="GeoJSON")

    return out_path


def run() -> Path:
    zip_path = download()
    grib_path = extract_zip(zip_path)
    return process(grib_path=grib_path, out_path=OUT)


def ingest_file(source: str, target: str) -> Path:
    # `source` is reserved for future multi-source ingestion. For now we run
    # the GloFAS flow and write to the requested target location.
    del source
    return process(grib_path=extract_zip(download()), out_path=Path(target))


if __name__ == "__main__":
    written = run()
    print(f"Wrote {written}")
