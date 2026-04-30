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
    ors_use_local: bool
    ors_local_directions_url: str | None
    ors_require_api_key: bool
    ors_directions_url: str
    ors_request_timeout_seconds: float
    routing_provider: str
    max_avoid_polygons: int
    simplify_tolerance_degrees: float
    ors_fallback_radius_meters: float
    eu_min_lon: float
    eu_max_lon: float
    eu_min_lat: float
    eu_max_lat: float
    custom_routing_graph_path: Path
    custom_routing_graph_metadata_path: Path
    custom_routing_osm_place: str | None
    custom_routing_osm_network_type: str
    custom_routing_simplify_graph: bool


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


def _env_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"Environment variable {name} must be a boolean "
        f"(one of: 1/0, true/false, yes/no, on/off), got: {raw!r}"
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    root_dir = _env_path("APP_ROOT_DIR", ROOT_DIR)
    default_artifact = _env_path("DEFAULT_ARTIFACT_PATH", root_dir / "data/processed/live_flood.geojson")
    frontend_index = _env_path("FRONTEND_INDEX_PATH", root_dir / "frontend/index.html")
    raw_dir = _env_path("GLOFAS_RAW_DIR", root_dir / "data/raw/glofas")
    zip_path = _env_path("GLOFAS_ZIP_PATH", raw_dir / "glofas_slovenia.zip")
    extract_dir = _env_path("GLOFAS_EXTRACT_DIR", raw_dir / "extracted")
    custom_routing_graph_path = _env_path(
        "CUSTOM_ROUTING_GRAPH_PATH",
        root_dir / "data/raw/osm/custom-routing.graphml",
    )
    remote_ors_url = os.getenv(
        "ORS_DIRECTIONS_URL",
        "https://api.openrouteservice.org/v2/directions/driving-car/geojson",
    )
    local_ors_url = os.getenv("ORS_LOCAL_DIRECTIONS_URL")
    use_local_ors = _env_bool("ORS_USE_LOCAL", bool(local_ors_url))
    active_ors_url = local_ors_url if use_local_ors and local_ors_url else remote_ors_url
    ors_require_api_key = _env_bool("ORS_REQUIRE_API_KEY", not use_local_ors)

    return Settings(
        root_dir=root_dir,
        default_artifact=default_artifact,
        frontend_index=frontend_index,
        raw_dir=raw_dir,
        zip_path=zip_path,
        extract_dir=extract_dir,
        ors_api_key=os.getenv("ORS_API_KEY"),
        ors_use_local=use_local_ors,
        ors_local_directions_url=local_ors_url,
        ors_require_api_key=ors_require_api_key,
        ors_directions_url=active_ors_url,
        ors_request_timeout_seconds=_env_float("ORS_REQUEST_TIMEOUT_SECONDS", 12.0),
        routing_provider=os.getenv("ROUTING_PROVIDER", "openrouteservice").strip().lower(),
        max_avoid_polygons=_env_int("MAX_AVOID_POLYGONS", 200),
        simplify_tolerance_degrees=_env_float("SIMPLIFY_TOLERANCE_DEGREES", 0.005),
        ors_fallback_radius_meters=_env_float("ORS_FALLBACK_RADIUS_METERS", 2000.0),
        eu_min_lon=_env_float("EU_MIN_LON", -25.0),
        eu_max_lon=_env_float("EU_MAX_LON", 45.0),
        eu_min_lat=_env_float("EU_MIN_LAT", 34.0),
        eu_max_lat=_env_float("EU_MAX_LAT", 72.0),
        custom_routing_graph_path=custom_routing_graph_path,
        custom_routing_graph_metadata_path=_env_path(
            "CUSTOM_ROUTING_GRAPH_METADATA_PATH",
            custom_routing_graph_path.with_suffix(".metadata.json"),
        ),
        custom_routing_osm_place=os.getenv("CUSTOM_ROUTING_OSM_PLACE"),
        custom_routing_osm_network_type=os.getenv("CUSTOM_ROUTING_OSM_NETWORK_TYPE", "drive"),
        custom_routing_simplify_graph=_env_bool("CUSTOM_ROUTING_SIMPLIFY_GRAPH", True),
    )


def reload_settings() -> None:
    get_settings.cache_clear()
