from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from api.config import get_settings
from api.ingestion import ingest_file
from api.routing import router as routing_router
from api.services import artifact_service, path_policy_service


app = FastAPI(title="Ingestion API")
app.include_router(routing_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
SETTINGS = get_settings()
DEFAULT_ARTIFACT = SETTINGS.default_artifact
FRONTEND_INDEX = SETTINGS.frontend_index
FRONTEND_DIR = FRONTEND_INDEX.parent

app.mount("/static/frontend", StaticFiles(directory=FRONTEND_DIR), name="frontend-static")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/", response_class=HTMLResponse)
def frontend() -> FileResponse:
    if not FRONTEND_INDEX.exists():
        raise HTTPException(status_code=404, detail="Frontend not found")
    return FileResponse(path=FRONTEND_INDEX, media_type="text/html")


@app.get("/geojson/live")
def geojson_live(source: str = Query("default", description="Ingestion source")) -> JSONResponse:
    artifact_path = artifact_service.ensure_artifact_exists(
        artifact_path=DEFAULT_ARTIFACT,
        source=source,
        ingest_fn=ingest_file,
    )
    payload = artifact_service.load_geojson_payload(artifact_path)
    return JSONResponse(content=payload)


@app.post("/artifact")
def get_or_build_artifact(
    target: str = Query(..., description="File path to return"),
    source: str = Query("default", description="Source used by ingestion when file is missing"),
) -> FileResponse:
    target_path = path_policy_service.resolve_artifact_path(target, settings=get_settings())
    output_path = artifact_service.ensure_output_file(
        target_path=target_path,
        source=source,
        ingest_fn=ingest_file,
    )
    return FileResponse(path=output_path, filename=output_path.name)
