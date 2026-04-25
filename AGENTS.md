# Repository Guidelines

## Project Structure & Module Organization
- `api/app.py`: FastAPI entrypoint with `/health` and `/artifact` endpoints.
- `api/ingestion.py`: ingestion pipeline (download, extract, transform, GeoJSON export).
- `data/raw/glofas/`: downloaded and extracted forecast inputs.
- `data/processed/`: generated artifacts (for example `live_flood.geojson`).
- `tmp/`: scratch outputs for local smoke checks.
- `requirements.txt`: pinned runtime dependencies.

Keep API orchestration in `api/app.py` and domain logic in `api/ingestion.py` (or additional modules under `api/` as the pipeline grows).

## Build, Test, and Development Commands
- `python3 -m venv .venv && . .venv/bin/activate`: create and activate virtualenv.
- `python -m pip install -r requirements.txt`: install dependencies.
- `uvicorn api.app:app --reload`: run API locally with auto-reload.
- `python api/ingestion.py`: run ingestion directly and write `data/processed/live_flood.geojson`.
- `curl -X POST 'http://127.0.0.1:8000/artifact?target=data/processed/live_flood.geojson&source=default'`: fetch existing artifact or trigger ingestion.

## Coding Style & Naming Conventions
- Follow PEP 8 with 4-space indentation and type hints (current code uses `Path`, typed returns, and `list[dict]`).
- Prefer `snake_case` for functions/variables and `UPPER_SNAKE_CASE` for module constants (for example `RAW_DIR`).
- Keep functions focused and side effects explicit (download/extract/process separated).
- Use concise error messages that explain recovery steps when possible.

## Testing Guidelines
- There is currently no formal test suite in this snapshot.
- Add tests under `tests/` using `pytest` (`test_*.py` naming).
- Prioritize unit tests for `_get_main_variable`, `_to_2d_grid`, and `process()` edge cases (missing vars, NaN-only grids, no GRIB files).
- For integration smoke checks, run API + `/artifact` against a small fixture in `tmp/`.

## Commit & Pull Request Guidelines
- Git metadata is not present in this workspace snapshot, so history-based conventions cannot be inferred here.
- Recommended commit style: `type(scope): summary` (e.g., `feat(ingestion): add fallback for missing cfgrib`).
- Keep commits focused and include validation steps in PR descriptions.
- PRs should include: purpose, behavior changes, test/smoke evidence, and sample output path(s) when data artifacts change.

## Security & Configuration Tips
- `cdsapi` requires credentials in `.cdsapirc`; never commit secrets.
- Treat `data/raw/` as transient input data; do not rely on large raw files being versioned.
