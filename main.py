"""PRG Agent — Microservizio per query spaziali sul PRG Piemonte"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os, glob, logging

from prg_query import PRGQuery
from downloader import ensure_shapefile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title="PRG Agent — Piemonte", version="1.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])

DATA_DIR = os.environ.get("DATA_DIR", "./data")
_prg_cache: dict[str, PRGQuery] = {}


def get_prg(comune: str) -> PRGQuery:
    key = comune.upper().strip()
    if key not in _prg_cache:
        comune_dir = os.path.join(DATA_DIR, key)
        shp_file = os.path.join(comune_dir, "dest_uso_polyg.shp")
        if not os.path.exists(shp_file):
            logger.info(f"Shapefile non trovato per {key}, download in corso...")
            success = ensure_shapefile(key, DATA_DIR)
            if not success:
                raise HTTPException(status_code=404,
                    detail=f"Shapefile PRG non disponibile per \'{key}\'. Scaricalo da geoportale.piemonte.it → data/{key}/")
        logger.info(f"Caricamento shapefile per {key}...")
        _prg_cache[key] = PRGQuery(comune_dir)
        logger.info(f"Shapefile {key} caricato ({_prg_cache[key].feature_count()} feature)")
    return _prg_cache[key]


class QueryRequest(BaseModel):
    comune: str
    lat: float
    lon: float
    buffer_m: Optional[float] = 5.0


class QueryResponse(BaseModel):
    comune: str
    coordinate: dict
    zona_urbanistica: Optional[dict]
    vincoli: list
    mod_intervento: list
    caratt_storica: list
    fonte: str
    note: Optional[str] = None


@app.get("/health")
def health():
    return {"status": "ok", "comuni_caricati": list(_prg_cache.keys()),
            "data_dir": DATA_DIR, "version": "1.1.0"}


@app.get("/debug")
def debug():
    """Mostra stato filesystem — per troubleshooting deploy"""
    data_ale = os.path.join(DATA_DIR, "ALESSANDRIA")
    chunks_dir = "/app/data_chunks"
    return {
        "data_dir_exists": os.path.exists(DATA_DIR),
        "alessandria_dir_exists": os.path.exists(data_ale),
        "shp_exists": os.path.exists(os.path.join(data_ale, "dest_uso_polyg.shp")),
        "alessandria_files": sorted(os.listdir(data_ale)) if os.path.exists(data_ale) else [],
        "chunks_dir_exists": os.path.exists(chunks_dir),
        "chunks_count": len(glob.glob(f"{chunks_dir}/chunk_*")) if os.path.exists(chunks_dir) else 0,
        "chunk_sizes": {os.path.basename(f): os.path.getsize(f) 
                        for f in sorted(glob.glob(f"{chunks_dir}/chunk_*"))[:3]}
    }


@app.get("/comuni")
def list_comuni():
    if not os.path.exists(DATA_DIR):
        return {"comuni": []}
    comuni = []
    for entry in os.listdir(DATA_DIR):
        entry_path = os.path.join(DATA_DIR, entry)
        if os.path.isdir(entry_path):
            has_shp = os.path.exists(os.path.join(entry_path, "dest_uso_polyg.shp"))
            comuni.append({"comune": entry, "shapefile_disponibile": has_shp, "in_cache": entry in _prg_cache})
    return {"comuni": comuni, "totale": len(comuni)}


@app.get("/metadata/{comune}")
def get_metadata(comune: str):
    return get_prg(comune).metadata()


@app.post("/query", response_model=QueryResponse)
def query_prg(req: QueryRequest):
    return get_prg(req.comune).query(lat=req.lat, lon=req.lon, buffer_m=req.buffer_m)


@app.post("/query/batch")
def query_prg_batch(requests: list[QueryRequest]):
    if len(requests) > 50:
        raise HTTPException(status_code=400, detail="Massimo 50 query per batch")
    results = []
    for req in requests:
        try:
            results.append({"success": True, "data": get_prg(req.comune).query(req.lat, req.lon, req.buffer_m)})
        except Exception as e:
            results.append({"success": False, "error": str(e), "comune": req.comune})
    return results


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
