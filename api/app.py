from __future__ import annotations

import json
from pathlib import Path

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse

from api.ingestion import ingest_file
from api.routing import router as routing_router


app = FastAPI(title="Ingestion API")
app.include_router(routing_router)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
ROOT_DIR = Path(__file__).resolve().parent.parent
DEFAULT_ARTIFACT = ROOT_DIR / "data/processed/live_flood.geojson"
FRONTEND_INDEX = ROOT_DIR / "frontend/index.html"


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
    artifact_path = DEFAULT_ARTIFACT

    if not artifact_path.exists():
        artifact_path = ingest_file(source=source, target=str(DEFAULT_ARTIFACT))

    try:
        payload = json.loads(artifact_path.read_text(encoding="utf-8"))
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Failed to read GeoJSON: {exc}") from exc

    return JSONResponse(content=payload)


@app.post("/artifact")
def get_or_build_artifact(
    target: str = Query(..., description="File path to return"),
    source: str = Query("default", description="Source used by ingestion when file is missing"),
) -> FileResponse:
    target_path = Path(target)

    if target_path.exists() and target_path.is_file():
        return FileResponse(path=target_path, filename=target_path.name)

    created_path = ingest_file(source=source, target=target)

    if not created_path.exists() or not created_path.is_file():
        raise HTTPException(status_code=500, detail="Ingestion finished but output file is missing")

    return FileResponse(path=created_path, filename=created_path.name)
