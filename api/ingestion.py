from __future__ import annotations

from datetime import datetime, timezone, timedelta
import logging
from pathlib import Path
import shutil
import zipfile

import cdsapi
import geopandas as gpd
import numpy as np
import xarray as xr
from shapely.geometry import Point

from api.config import Settings, get_settings

LOGGER = logging.getLogger(__name__)


def download(target_path: Path | None = None, *, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    target_path = target_path or settings.zip_path
    target_path.parent.mkdir(parents=True, exist_ok=True)
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
            LOGGER.info("glofas_download_started date=%s target_path=%s", date.date(), target_path)
            client.retrieve(
                "cems-glofas-forecast",
                request,
                str(target_path),
            )
            LOGGER.info("glofas_download_succeeded date=%s target_path=%s", date.date(), target_path)
            return target_path

        except Exception as e:
            LOGGER.warning("glofas_download_failed date=%s error=%s", date.date(), e)

    raise RuntimeError("No valid GloFAS forecast found in the last 7 days.")


def extract_zip(
    zip_path: Path | None = None,
    *,
    extract_dir: Path | None = None,
    settings: Settings | None = None,
) -> Path:
    settings = settings or get_settings()
    zip_path = zip_path or settings.zip_path
    extract_dir = extract_dir or settings.extract_dir
    extract_dir.mkdir(parents=True, exist_ok=True)

    _clear_directory(extract_dir)

    with zipfile.ZipFile(zip_path, "r") as z:
        base_dir = extract_dir.resolve(strict=False)
        members = z.infolist()
        for member in members:
            member_target = (extract_dir / member.filename).resolve(strict=False)
            if not (member_target == base_dir or member_target.is_relative_to(base_dir)):
                raise RuntimeError(f"Unsafe ZIP member path detected: {member.filename!r}")
        for member in members:
            z.extract(member, extract_dir)

    grib_files = list(extract_dir.rglob("*.grib")) + list(extract_dir.rglob("*.grib2"))

    if not grib_files:
        raise RuntimeError("No GRIB files found in downloaded ZIP.")

    return grib_files[0]


def _clear_directory(directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for item in directory.iterdir():
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()


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


def _is_in_europe(lat: float, lon: float, *, settings: Settings) -> bool:
    return settings.eu_min_lat <= lat <= settings.eu_max_lat and settings.eu_min_lon <= lon <= settings.eu_max_lon


def process(grib_path: Path, out_path: Path | None = None, *, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    out_path = out_path or settings.default_artifact
    out_path.parent.mkdir(parents=True, exist_ok=True)
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

            if not _is_in_europe(lat=lat, lon=lon, settings=settings):
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


def run(*, settings: Settings | None = None) -> Path:
    settings = settings or get_settings()
    zip_path = download(settings=settings)
    grib_path = extract_zip(zip_path=zip_path, settings=settings)
    return process(grib_path=grib_path, out_path=settings.default_artifact, settings=settings)


def ingest_file(source: str, target: str) -> Path:
    # `source` is reserved for future multi-source ingestion. For now we run
    # the GloFAS flow and write to the requested target location.
    del source
    settings = get_settings()
    return process(
        grib_path=extract_zip(zip_path=download(settings=settings), settings=settings),
        out_path=Path(target),
        settings=settings,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    written = run()
    LOGGER.info("glofas_ingestion_completed output_path=%s", written)
