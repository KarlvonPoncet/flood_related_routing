from __future__ import annotations

import json
import logging
import re
import socket
from pathlib import Path
from urllib.parse import urlparse
from time import perf_counter
from typing import Any, Callable, Protocol
from urllib import error, request

from fastapi import HTTPException

from api.config import get_settings
from api.services.routing_geometry_service import build_avoid_polygons, load_high_risk_geometries

LOGGER = logging.getLogger(__name__)


class CoordinateLike(Protocol):
    lat: float
    lon: float


class RoutingProviderError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class AvoidAreaError(RoutingProviderError):
    pass


class UnroutablePointError(RoutingProviderError):
    pass


class DistanceLimitError(RoutingProviderError):
    def __init__(self, message: str, *, max_distance_meters: float | None = None) -> None:
        super().__init__(message)
        self.max_distance_meters = max_distance_meters


class RoutingProvider(Protocol):
    name: str
    warning_label: str

    def route(
        self,
        *,
        start: CoordinateLike,
        end: CoordinateLike,
        avoid_polygons: dict[str, Any] | None,
        radiuses: list[float] | None = None,
    ) -> dict[str, Any]:
        ...


class OpenRouteServiceProvider:
    name = "openrouteservice"
    warning_label = "ORS"

    def route(
        self,
        *,
        start: CoordinateLike,
        end: CoordinateLike,
        avoid_polygons: dict[str, Any] | None,
        radiuses: list[float] | None = None,
    ) -> dict[str, Any]:
        return call_openrouteservice(
            start=start,
            end=end,
            avoid_polygons=avoid_polygons,
            radiuses=radiuses,
        )

def get_routing_provider() -> RoutingProvider:
    settings = get_settings()
    if settings.routing_provider in {"openrouteservice", "ors"}:
        return OpenRouteServiceProvider()
    raise HTTPException(
        status_code=500,
        detail=(
            f"Unsupported ROUTING_PROVIDER {settings.routing_provider!r}. "
            "Available providers: openrouteservice"
        ),
    )


def call_openrouteservice(
    *,
    start: CoordinateLike,
    end: CoordinateLike,
    avoid_polygons: dict[str, Any] | None,
    radiuses: list[float] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if settings.ors_use_local and not settings.ors_local_directions_url:
        raise HTTPException(
            status_code=500,
            detail="ORS_USE_LOCAL is enabled but ORS_LOCAL_DIRECTIONS_URL is not set",
        )

    api_key = settings.ors_api_key
    if settings.ors_require_api_key and not api_key:
        raise HTTPException(status_code=500, detail="Missing ORS_API_KEY environment variable")

    base_body: dict[str, Any] = {
        "coordinates": [
            [start.lon, start.lat],
            [end.lon, end.lat],
        ],
    }
    if radiuses is not None:
        base_body["radiuses"] = radiuses
    if avoid_polygons is not None:
        base_body["options"] = {"avoid_polygons": avoid_polygons}

    request_started = perf_counter()
    LOGGER.info(
        "ors_request_started url=%s timeout_seconds=%.1f has_avoid_polygons=%s has_radiuses=%s",
        settings.ors_directions_url,
        settings.ors_request_timeout_seconds,
        avoid_polygons is not None,
        radiuses is not None,
    )

    try:
        response_payload = _post_ors_json(
            url=settings.ors_directions_url,
            body=base_body,
            headers=_ors_headers(api_key),
            timeout_seconds=settings.ors_request_timeout_seconds,
        )
    except HTTPException as exc:
        if settings.ors_use_local and _is_ors_unsupported_format_error(exc):
            local_json_url = _geojson_to_json_url(settings.ors_directions_url)
            fallback_body = dict(base_body)
            fallback_body["geometry_format"] = "geojson"
            LOGGER.warning(
                "ors_request_retrying_json_endpoint url=%s fallback_url=%s",
                settings.ors_directions_url,
                local_json_url,
            )
            try:
                response_payload = _post_ors_json(
                    url=local_json_url,
                    body=fallback_body,
                    headers=_ors_headers(api_key),
                    timeout_seconds=settings.ors_request_timeout_seconds,
                )
            except HTTPException as fallback_exc:
                raise _to_provider_error(fallback_exc) from fallback_exc
        else:
            LOGGER.warning(
                "ors_request_failed duration_ms=%.1f detail=%s",
                (perf_counter() - request_started) * 1000,
                exc.detail,
            )
            raise _to_provider_error(exc) from exc

    LOGGER.info("ors_request_succeeded duration_ms=%.1f", (perf_counter() - request_started) * 1000)
    return _normalize_ors_route_payload(response_payload)


def is_ors_avoid_polygon_area_error(exc: HTTPException) -> bool:
    if exc.status_code != 502:
        return False
    detail = str(exc.detail)
    return "\"code\":2003" in detail and "polygon to avoid" in detail


def is_ors_unroutable_point_error(exc: HTTPException) -> bool:
    if exc.status_code != 502:
        return False
    detail = str(exc.detail)
    return "\"code\":2010" in detail and "routable point" in detail


def is_ors_distance_limit_error(exc: HTTPException) -> bool:
    if exc.status_code != 502:
        return False
    detail = str(exc.detail)
    return "\"code\":2004" in detail and "must not be greater than" in detail


def _is_ors_unsupported_format_error(exc: HTTPException) -> bool:
    if exc.status_code != 502:
        return False
    detail = str(exc.detail)
    return "\"code\":2007" in detail and "format is not supported" in detail


def _geojson_to_json_url(url: str) -> str:
    if url.endswith("/geojson"):
        return f"{url[:-8]}/json"
    return url


def _post_ors_json(
    *,
    url: str,
    body: dict[str, Any],
    headers: dict[str, str],
    timeout_seconds: float,
) -> dict[str, Any]:
    payload = json.dumps(body).encode("utf-8")
    req = request.Request(
        url,
        data=payload,
        method="POST",
        headers=headers,
    )

    try:
        with request.urlopen(req, timeout=timeout_seconds) as response:
            response_bytes = response.read()
    except error.HTTPError as exc:
        error_body = exc.read().decode("utf-8", errors="replace")
        raise HTTPException(
            status_code=502,
            detail=f"OpenRouteService request failed ({exc.code}): {error_body}",
        ) from exc
    except error.URLError as exc:
        if _is_timeout_error(exc):
            parsed = urlparse(url)
            host_port = parsed.netloc or parsed.path
            raise HTTPException(
                status_code=502,
                detail=(
                    "OpenRouteService request timed out "
                    f"after {timeout_seconds:.1f}s while connecting to {host_port}. "
                    "Verify ORS is running and reachable from the API container."
                ),
            ) from exc
        raise HTTPException(status_code=502, detail=f"OpenRouteService request failed: {exc}") from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"OpenRouteService request failed: {exc}") from exc

    try:
        parsed = json.loads(response_bytes.decode("utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Invalid OpenRouteService response: {exc}") from exc

    if not isinstance(parsed, dict):
        raise HTTPException(status_code=502, detail="Invalid OpenRouteService response: expected JSON object")
    return parsed


def _is_timeout_error(exc: error.URLError) -> bool:
    reason = getattr(exc, "reason", None)
    if isinstance(reason, TimeoutError):
        return True
    if isinstance(reason, socket.timeout):
        return True
    return "timed out" in str(exc).lower()


def _extract_ors_distance_limit_meters(detail: str) -> float | None:
    match = re.search(r"must not be greater than ([0-9.]+) meters", detail)
    if not match:
        return None
    try:
        return float(match.group(1))
    except ValueError:
        return None


def _to_provider_error(exc: HTTPException) -> RoutingProviderError:
    if is_ors_avoid_polygon_area_error(exc):
        return AvoidAreaError(str(exc.detail))
    if is_ors_unroutable_point_error(exc):
        return UnroutablePointError(str(exc.detail))
    if is_ors_distance_limit_error(exc):
        return DistanceLimitError(
            str(exc.detail),
            max_distance_meters=_extract_ors_distance_limit_meters(str(exc.detail)),
        )
    return RoutingProviderError(str(exc.detail))


def _normalize_ors_route_payload(payload: dict[str, Any]) -> dict[str, Any]:
    if payload.get("type") == "FeatureCollection":
        return payload

    routes = payload.get("routes")
    if not isinstance(routes, list) or not routes:
        return payload

    first_route = routes[0]
    if not isinstance(first_route, dict):
        return payload

    geometry = first_route.get("geometry")
    normalized_geometry: dict[str, Any] | None = None
    if isinstance(geometry, dict) and geometry.get("type") and geometry.get("coordinates"):
        normalized_geometry = geometry
    elif isinstance(geometry, list):
        normalized_geometry = {"type": "LineString", "coordinates": geometry}

    if normalized_geometry is None:
        return payload

    summary = first_route.get("summary", {})
    feature = {
        "type": "Feature",
        "geometry": normalized_geometry,
        "properties": {
            "summary": summary if isinstance(summary, dict) else {},
        },
    }
    return {
        "type": "FeatureCollection",
        "features": [feature],
    }


def _ors_headers(api_key: str | None) -> dict[str, str]:
    headers = {
        "Content-Type": "application/json",
        "Accept": "application/geo+json, application/json",
    }
    if api_key:
        headers["Authorization"] = api_key
    return headers


def compute_flood_aware_route(
    *,
    start: CoordinateLike,
    end: CoordinateLike,
    artifact_path: Path,
    load_geometries_fn: Callable[[Path], list[Any]],
    build_avoid_fn: Callable[[list[Any]], dict[str, Any] | None],
    fallback_radius_meters: float,
    call_route_fn: Callable[..., dict[str, Any]] | None = None,
    routing_provider: RoutingProvider | None = None,
) -> dict[str, Any]:
    if routing_provider is None:
        routing_provider = get_routing_provider()
    if call_route_fn is None:
        call_route_fn = routing_provider.route
    provider_label = routing_provider.warning_label

    geometries = load_geometries_fn(artifact_path)
    active_geometry_count = len(geometries)
    avoid_polygons = build_avoid_fn(geometries)
    if avoid_polygons is None:
        active_geometry_count = 0
    route_warnings: list[str] = []
    radiuses: list[float] | None = None
    attempt = 0

    while True:
        attempt += 1
        attempt_started = perf_counter()
        LOGGER.info(
            "flood_route_attempt_started attempt=%d avoid_polygons=%s radiuses=%s active_polygons=%d",
            attempt,
            avoid_polygons is not None,
            radiuses is not None,
            active_geometry_count,
        )
        try:
            route = call_route_fn(
                start=start,
                end=end,
                avoid_polygons=avoid_polygons,
                radiuses=radiuses,
            )
            LOGGER.info(
                "flood_route_attempt_succeeded attempt=%d duration_ms=%.1f",
                attempt,
                (perf_counter() - attempt_started) * 1000,
            )
            break
        except AvoidAreaError:
            LOGGER.warning(
                "flood_route_attempt_failed attempt=%d duration_ms=%.1f status=%s detail=%s",
                attempt,
                (perf_counter() - attempt_started) * 1000,
                502,
                "avoid area rejected",
            )
            if avoid_polygons is not None:
                next_geometry_count = active_geometry_count // 2
                next_avoid_polygons: dict[str, Any] | None = None

                while next_geometry_count > 0:
                    candidate = build_avoid_fn(geometries[:next_geometry_count])
                    if candidate is not None:
                        next_avoid_polygons = candidate
                        break
                    next_geometry_count //= 2

                if next_avoid_polygons is not None:
                    active_geometry_count = next_geometry_count
                    avoid_polygons = next_avoid_polygons
                    route_warnings.append(
                        f"{provider_label} rejected avoid_polygons area; "
                        f"retried with {active_geometry_count} nearest polygons."
                    )
                    LOGGER.warning(
                        "flood_route_retrying_with_fewer_polygons next_active_polygons=%d",
                        active_geometry_count,
                    )
                    continue

                avoid_polygons = None
                active_geometry_count = 0
                route_warnings.append(
                    f"{provider_label} rejected avoid_polygons due to area limit; "
                    "returned route without flood avoidance polygons."
                )
                LOGGER.warning("flood_route_retrying_without_avoid_polygons")
                continue

            LOGGER.error("flood_route_failed_non_retriable attempt=%d", attempt)
            raise HTTPException(status_code=502, detail="Provider rejected avoid polygons area")
        except UnroutablePointError:
            LOGGER.warning(
                "flood_route_attempt_failed attempt=%d duration_ms=%.1f status=%s detail=%s",
                attempt,
                (perf_counter() - attempt_started) * 1000,
                502,
                "unroutable point",
            )
            if radiuses is None:
                radiuses = [fallback_radius_meters, fallback_radius_meters]
                route_warnings.append(
                    f"{provider_label} could not snap one or more waypoints with default radius; "
                    f"retried with {fallback_radius_meters:.0f}m radiuses."
                )
                LOGGER.warning(
                    "flood_route_retrying_with_custom_radiuses radius_meters=%.0f",
                    fallback_radius_meters,
                )
                continue

            LOGGER.error("flood_route_failed_non_retriable attempt=%d", attempt)
            raise HTTPException(status_code=502, detail="Provider could not route waypoints")
        except DistanceLimitError as exc:
            LOGGER.warning(
                "flood_route_attempt_failed attempt=%d duration_ms=%.1f status=%s detail=%s",
                attempt,
                (perf_counter() - attempt_started) * 1000,
                502,
                exc.message,
            )
            if avoid_polygons is not None:
                avoid_polygons = None
                active_geometry_count = 0
                route_warnings.append(
                    f"{provider_label} rejected route due to max distance constraint; "
                    "retried without flood avoidance polygons."
                )
                LOGGER.warning("flood_route_retrying_without_avoid_polygons_due_to_distance_limit")
                continue

            if exc.max_distance_meters is not None:
                detail = (
                    f"Route exceeds configured {provider_label} maximum distance "
                    f"({exc.max_distance_meters:.0f} meters). "
                    f"Choose closer points or increase the {provider_label} routing distance limit."
                )
            else:
                detail = (
                    f"Route exceeds configured {provider_label} maximum distance. "
                    f"Choose closer points or increase the {provider_label} routing distance limit."
                )
            LOGGER.warning("flood_route_failed_distance_limit max_distance_meters=%s", exc.max_distance_meters)
            raise HTTPException(status_code=422, detail=detail) from exc
        except RoutingProviderError as exc:
            LOGGER.error("flood_route_failed_non_retriable attempt=%d", attempt)
            raise HTTPException(status_code=502, detail=f"{provider_label} provider error: {exc.message}") from exc
        except HTTPException:
            LOGGER.error("flood_route_failed_non_retriable attempt=%d", attempt)
            raise

    response = {
        "artifact_path": str(artifact_path),
        "high_risk_polygon_count": len(geometries),
        "avoidance_polygon_count": active_geometry_count,
        "using_avoid_polygons": avoid_polygons is not None,
        "using_custom_radiuses": radiuses is not None,
        "route": route,
    }
    if route_warnings:
        response["warning"] = " ".join(route_warnings)
    LOGGER.info(
        "flood_route_completed attempts=%d high_risk_polygon_count=%d avoidance_polygon_count=%d "
        "using_avoid_polygons=%s using_custom_radiuses=%s",
        attempt,
        len(geometries),
        active_geometry_count,
        avoid_polygons is not None,
        radiuses is not None,
    )
    return response
