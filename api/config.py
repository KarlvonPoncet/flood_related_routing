from __future__ import annotations

import os
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


ROOT_DIR = Path(__file__).resolve().parent.parent


@dataclass(frozen=True)
class Settings:
    root_dir: Path
    default_artifact: Path
    frontend_index: Path
    raw_dir: Path
    zip_path: Path
    extract_dir: Path
    ors_api_key: str | None
    ors_directions_url: str
    max_avoid_polygons: int
    simplify_tolerance_degrees: float
    eu_min_lon: float
    eu_max_lon: float
    eu_min_lat: float
    eu_max_lat: float


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be an integer, got: {raw!r}") from exc


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"Environment variable {name} must be a float, got: {raw!r}") from exc


def _env_path(name: str, default: Path) -> Path:
    raw = os.getenv(name)
    if not raw:
        return default
    return Path(raw).expanduser()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root_dir = _env_path("APP_ROOT_DIR", ROOT_DIR)
    default_artifact = _env_path("DEFAULT_ARTIFACT_PATH", root_dir / "data/processed/live_flood.geojson")
    frontend_index = _env_path("FRONTEND_INDEX_PATH", root_dir / "frontend/index.html")
    raw_dir = _env_path("GLOFAS_RAW_DIR", root_dir / "data/raw/glofas")
    zip_path = _env_path("GLOFAS_ZIP_PATH", raw_dir / "glofas_slovenia.zip")
    extract_dir = _env_path("GLOFAS_EXTRACT_DIR", raw_dir / "extracted")

    return Settings(
        root_dir=root_dir,
        default_artifact=default_artifact,
        frontend_index=frontend_index,
        raw_dir=raw_dir,
        zip_path=zip_path,
        extract_dir=extract_dir,
        ors_api_key=os.getenv("ORS_API_KEY"),
        ors_directions_url=os.getenv(
            "ORS_DIRECTIONS_URL",
            "https://api.openrouteservice.org/v2/directions/driving-car/geojson",
        ),
        max_avoid_polygons=_env_int("MAX_AVOID_POLYGONS", 200),
        simplify_tolerance_degrees=_env_float("SIMPLIFY_TOLERANCE_DEGREES", 0.005),
        eu_min_lon=_env_float("EU_MIN_LON", -25.0),
        eu_max_lon=_env_float("EU_MAX_LON", 45.0),
        eu_min_lat=_env_float("EU_MIN_LAT", 34.0),
        eu_max_lat=_env_float("EU_MAX_LAT", 72.0),
    )


def reload_settings() -> None:
    get_settings.cache_clear()
