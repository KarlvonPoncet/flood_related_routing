from __future__ import annotations

from pathlib import Path
import zipfile

import numpy as np
import pytest
import xarray as xr

from api import ingestion


def test_get_main_variable_prefers_named_discharge_var() -> None:
    ds = xr.Dataset(
        {
            "river_discharge_in_the_last_24_hours": (
                ("latitude", "longitude"),
                np.ones((2, 2)),
            ),
            "other": (("latitude", "longitude"), np.zeros((2, 2))),
        }
    )

    assert ingestion._get_main_variable(ds) == "river_discharge_in_the_last_24_hours"


def test_get_main_variable_falls_back_to_first_var() -> None:
    ds = xr.Dataset({"dis24": (("latitude", "longitude"), np.ones((2, 2)))})

    assert ingestion._get_main_variable(ds) == "dis24"


def test_get_main_variable_raises_when_dataset_has_no_data_vars() -> None:
    ds = xr.Dataset(coords={"latitude": [46.0], "longitude": [14.0]})

    with pytest.raises(RuntimeError, match="No data variables found"):
        ingestion._get_main_variable(ds)


def test_to_2d_grid_reduces_non_spatial_dimensions() -> None:
    arr = xr.DataArray(
        np.arange(2 * 3 * 4).reshape(2, 3, 4),
        dims=("step", "latitude", "longitude"),
    )

    grid = ingestion._to_2d_grid(arr)

    assert grid.shape == (3, 4)
    np.testing.assert_array_equal(grid, arr.isel(step=0).values)


def test_open_glofas_grib_wraps_missing_cfgrib_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _raise(*args: object, **kwargs: object) -> xr.Dataset:
        raise ValueError("unrecognized engine 'cfgrib'")

    monkeypatch.setattr(ingestion.xr, "open_dataset", _raise)

    with pytest.raises(RuntimeError, match="Install cfgrib"):
        ingestion.open_glofas_grib(Path("fake.grib2"))


def test_extract_zip_raises_when_no_grib_files(
    tmp_path: Path,
) -> None:
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()

    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("readme.txt", "not a grib file")

    with pytest.raises(RuntimeError, match="No GRIB files found"):
        ingestion.extract_zip(zip_path=zip_path, extract_dir=extract_dir)


def test_extract_zip_returns_first_grib_file(
    tmp_path: Path,
) -> None:
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()

    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("forecast.grib2", "binary")

    grib_path = ingestion.extract_zip(zip_path=zip_path, extract_dir=extract_dir)

    assert grib_path == extract_dir / "forecast.grib2"
    assert grib_path.exists()


def test_extract_zip_clears_nested_files_before_extracting(tmp_path: Path) -> None:
    extract_dir = tmp_path / "extracted"
    nested = extract_dir / "stale" / "old"
    nested.mkdir(parents=True)
    (nested / "stale.txt").write_text("stale", encoding="utf-8")

    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("fresh.grib2", "binary")

    grib_path = ingestion.extract_zip(zip_path=zip_path, extract_dir=extract_dir)

    assert grib_path == extract_dir / "fresh.grib2"
    assert not (extract_dir / "stale").exists()


def test_extract_zip_rejects_path_traversal_member(tmp_path: Path) -> None:
    extract_dir = tmp_path / "extracted"
    extract_dir.mkdir()
    zip_path = tmp_path / "sample.zip"
    with zipfile.ZipFile(zip_path, "w") as zf:
        zf.writestr("../escape.grib2", "binary")

    with pytest.raises(RuntimeError, match="Unsafe ZIP member path"):
        ingestion.extract_zip(zip_path=zip_path, extract_dir=extract_dir)


def test_process_raises_when_lat_lon_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    ds = xr.Dataset({"dis24": (("x", "y"), np.ones((2, 2)))})
    monkeypatch.setattr(ingestion, "open_glofas_grib", lambda _: ds)

    with pytest.raises(RuntimeError, match="latitude/longitude"):
        ingestion.process(Path("fake.grib2"), out_path=Path("unused.geojson"))


def test_process_skips_nan_and_low_values_and_emits_expected_risk_levels(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    lats = np.array([50.0, 51.0, 52.0, 53.0])
    lons = np.array([10.0, 11.0, 12.0, 13.0])
    discharge = np.zeros((4, 4), dtype=float)

    # sampled cells are [0,0], [0,2], [2,0], [2,2] due to step=2
    discharge[0, 0] = 600.0   # low (0.2)
    discharge[0, 2] = 3000.0  # high (1.0)
    discharge[2, 0] = 1200.0  # medium (0.4)
    discharge[2, 2] = np.nan  # skipped

    ds = xr.Dataset(
        {
            "river_discharge_in_the_last_24_hours": (
                ("latitude", "longitude"),
                discharge,
            )
        },
        coords={"latitude": lats, "longitude": lons},
    )

    monkeypatch.setattr(ingestion, "open_glofas_grib", lambda _: ds)

    captured: dict[str, object] = {}

    class DummyGeoDataFrame:
        def __init__(self, features: list[dict], crs: str) -> None:
            self.features = features
            self.crs = crs

        def to_file(self, out_path: Path, driver: str) -> None:
            captured["out_path"] = Path(out_path)
            captured["driver"] = driver
            captured["features"] = self.features
            Path(out_path).write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

    def _from_features(features: list[dict], crs: str) -> DummyGeoDataFrame:
        return DummyGeoDataFrame(features=features, crs=crs)

    monkeypatch.setattr(
        ingestion.gpd.GeoDataFrame,
        "from_features",
        staticmethod(_from_features),
    )

    out_path = tmp_path / "live.geojson"
    written = ingestion.process(Path("fake.grib2"), out_path=out_path)

    assert written == out_path
    assert out_path.exists()
    assert captured["driver"] == "GeoJSON"

    features = captured["features"]
    assert isinstance(features, list)
    assert len(features) == 3

    levels = sorted(feature["properties"]["risk_level"] for feature in features)
    assert levels == ["high", "low", "medium"]


def test_process_handles_all_nan_grid_with_empty_feature_collection(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    ds = xr.Dataset(
        {
            "river_discharge_in_the_last_24_hours": (
                ("latitude", "longitude"),
                np.full((2, 2), np.nan),
            )
        },
        coords={"latitude": np.array([50.0, 52.0]), "longitude": np.array([10.0, 12.0])},
    )
    monkeypatch.setattr(ingestion, "open_glofas_grib", lambda _: ds)

    captured: dict[str, object] = {}

    class DummyGeoDataFrame:
        def __init__(self, features: list[dict], crs: str) -> None:
            self.features = features
            self.crs = crs

        def to_file(self, out_path: Path, driver: str) -> None:
            captured["features"] = self.features
            Path(out_path).write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")

    def _from_features(features: list[dict], crs: str) -> DummyGeoDataFrame:
        return DummyGeoDataFrame(features=features, crs=crs)

    monkeypatch.setattr(
        ingestion.gpd.GeoDataFrame,
        "from_features",
        staticmethod(_from_features),
    )

    out_path = tmp_path / "live.geojson"
    written = ingestion.process(Path("fake.grib2"), out_path=out_path)

    assert written == out_path
    assert out_path.exists()
    assert captured["features"] == []


def test_run_uses_runtime_default_artifact_after_reload(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    first = tmp_path / "first.geojson"
    second = tmp_path / "second.geojson"
    zip_path = tmp_path / "fake.zip"
    grib_path = tmp_path / "fake.grib2"
    raw_dir = tmp_path / "raw"
    extract_dir = tmp_path / "extract"
    raw_dir.mkdir()
    extract_dir.mkdir()

    def _download(*, target_path=None, settings=None):
        del target_path, settings
        return zip_path

    def _extract_zip(*, zip_path=None, extract_dir=None, settings=None):
        del zip_path, extract_dir, settings
        return grib_path

    observed_out_paths: list[Path] = []

    def _process(*, grib_path, out_path=None, settings=None):
        del grib_path, settings
        assert out_path is not None
        observed_out_paths.append(Path(out_path))
        Path(out_path).write_text('{"type":"FeatureCollection","features":[]}', encoding="utf-8")
        return Path(out_path)

    monkeypatch.setattr(ingestion, "download", _download)
    monkeypatch.setattr(ingestion, "extract_zip", _extract_zip)
    monkeypatch.setattr(ingestion, "process", _process)

    monkeypatch.setenv("APP_ROOT_DIR", str(tmp_path))
    monkeypatch.setenv("GLOFAS_RAW_DIR", str(raw_dir))
    monkeypatch.setenv("GLOFAS_EXTRACT_DIR", str(extract_dir))

    from api import config as config_module

    try:
        monkeypatch.setenv("DEFAULT_ARTIFACT_PATH", str(first))
        config_module.reload_settings()
        out1 = ingestion.run()
        assert out1 == first

        monkeypatch.setenv("DEFAULT_ARTIFACT_PATH", str(second))
        config_module.reload_settings()
        out2 = ingestion.run()
        assert out2 == second
    finally:
        config_module.reload_settings()

    assert observed_out_paths == [first, second]
