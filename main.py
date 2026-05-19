"""
PRG Agent — Microservizio per query spaziali sul PRG Piemonte
Mosaicatura PRG Regione Piemonte (shapefile)

Endpoints:
  GET  /health               — health check
  POST /query                — query zona + vincoli per lat/lon + comune
  GET  /comuni               — lista comuni disponibili
  GET  /metadata/{comune}    — metadata shapefile comune
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os
import logging

from prg_query import PRGQuery
from downloader import ensure_shapefile

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="PRG Agent — Piemonte",
    description="Microservizio per query spaziali sul PRG Piemonte (Mosaicatura regionale)",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_DIR = os.environ.get("DATA_DIR", "./data")

# Cache in-memory delle query PRG (per performance)
_prg_cache: dict[str, PRGQuery] = {}


def get_prg(comune: str) -> PRGQuery:
    """Carica o recupera dalla cache il PRGQuery per un comune."""
    key = comune.upper().strip()
    if key not in _prg_cache:
        comune_dir = os.path.join(DATA_DIR, key)
        if not os.path.exists(comune_dir):
            # Prova a scaricare dal Geoportale Piemonte
            logger.info(f"Shapefile non trovato per {key}, download in corso...")
            success = ensure_shapefile(key, DATA_DIR)
            if not success:
                raise HTTPException(
                    status_code=404,
                    detail=f"Shapefile PRG non disponibile per il comune '{key}'. "
                           f"Scaricalo da geoportale.piemonte.it e caricalo in data/{key}/"
                )
        logger.info(f"Caricamento shapefile per {key}...")
        _prg_cache[key] = PRGQuery(comune_dir)
        logger.info(f"Shapefile {key} caricato ({_prg_cache[key].feature_count()} feature)")
    return _prg_cache[key]


class QueryRequest(BaseModel):
    comune: str               # Nome comune (es. "alessandria", "torino")
    lat: float                # Latitudine WGS84
    lon: float                # Longitudine WGS84
    buffer_m: Optional[float] = 5.0  # Buffer in metri per il fallback nearest


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
    return {
        "status": "ok",
        "comuni_caricati": list(_prg_cache.keys()),
        "data_dir": DATA_DIR
    }


@app.get("/comuni")
def list_comuni():
    """Lista dei comuni disponibili (shapefile presenti in data/)."""
    if not os.path.exists(DATA_DIR):
        return {"comuni": []}
    comuni = []
    for entry in os.listdir(DATA_DIR):
        entry_path = os.path.join(DATA_DIR, entry)
        if os.path.isdir(entry_path):
            # Verifica che abbia almeno il file principale
            has_shp = os.path.exists(os.path.join(entry_path, "dest_uso_polyg.shp"))
            comuni.append({
                "comune": entry,
                "shapefile_disponibile": has_shp,
                "in_cache": entry in _prg_cache
            })
    return {"comuni": comuni, "totale": len(comuni)}


@app.get("/metadata/{comune}")
def get_metadata(comune: str):
    """Metadata e statistiche sul shapefile di un comune."""
    prg = get_prg(comune)
    return prg.metadata()


@app.post("/query", response_model=QueryResponse)
def query_prg(req: QueryRequest):
    """
    Query principale: dato lat/lon e comune, restituisce:
    - Zona urbanistica (destinazione d'uso, compromissione, caratteristica)
    - Vincoli PRG (con codice e descrizione)
    - Modalità di intervento
    - Caratterizzazione storica (se presente)
    """
    prg = get_prg(req.comune)
    result = prg.query(lat=req.lat, lon=req.lon, buffer_m=req.buffer_m)
    return result


@app.post("/query/batch")
def query_prg_batch(requests: list[QueryRequest]):
    """Query multipla per più punti (max 50)."""
    if len(requests) > 50:
        raise HTTPException(status_code=400, detail="Massimo 50 query per batch")
    results = []
    for req in requests:
        try:
            prg = get_prg(req.comune)
            result = prg.query(lat=req.lat, lon=req.lon, buffer_m=req.buffer_m)
            results.append({"success": True, "data": result})
        except Exception as e:
            results.append({"success": False, "error": str(e), "comune": req.comune})
    return results


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=int(os.environ.get("PORT", 8000)))
