"""PRG Agent — Microservizio per query spaziali sul PRG Piemonte"""
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Optional
import os, glob, logging, subprocess, zipfile
from prg_query import PRGQuery
from downloader import ensure_shapefile
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
# === STARTUP: assembla shapefile da chunk se necessario ===
def assemble_shapefile_from_chunks():
    data_dir = os.environ.get("DATA_DIR", "./data")
    shp_file = os.path.join(data_dir, "ALESSANDRIA", "dest_uso_polyg.shp")
    chunks_dir = "/app/data_chunks"
    
    if os.path.exists(shp_file):
        logger.info("Shapefile Alessandria già presente")
        return
    
    chunks = sorted(glob.glob(f"{chunks_dir}/chunk_*"))
    if not chunks:
        logger.warning("Nessun chunk trovato in /app/data_chunks/")
        return
    
    logger.info(f"Assemblo ZIP da {len(chunks)} chunk...")
    zip_path = "/tmp/alessandria_assembled.zip"
    
    try:
        with open(zip_path, "wb") as out:
            for chunk_file in chunks:
                with open(chunk_file, "rb") as f:
                    data = f.read()
                    out.write(data)
                    logger.info(f"  + {os.path.basename(chunk_file)}: {len(data)} bytes")
        
        zip_size = os.path.getsize(zip_path)
        logger.info(f"ZIP assemblato: {zip_size} bytes")
        
        target_dir = os.path.join(data_dir, "ALESSANDRIA")
        os.makedirs(target_dir, exist_ok=True)
        
        with zipfile.ZipFile(zip_path, "r") as zf:
            namelist = zf.namelist()
            logger.info(f"File nel ZIP: {namelist}")
            zf.extractall(target_dir)
        
        os.remove(zip_path)
        
        extracted = os.listdir(target_dir)
        logger.info(f"Estratti {len(extracted)} file in {target_dir}: {extracted}")
        
        if os.path.exists(shp_file):
            logger.info("✅ Shapefile Alessandria assemblato con successo!")
        else:
            logger.error(f"❌ dest_uso_polyg.shp non trovato dopo estrazione. File presenti: {extracted}")
            
    except Exception as e:
        logger.error(f"❌ Errore assembly: {e}")
        import traceback
        logger.error(traceback.format_exc())
# Esegui assembly all\'avvio
assemble_shapefile_from_chunks()
app = FastAPI(title="PRG Agent — Piemonte", version="1.2.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True,
                   allow_methods=["*"], allow_headers=["*"])
# === NTA reader (Norme Tecniche di Attuazione) ===
from nta_reader import router as nta_router
app.include_router(nta_router)
DATA_DIR = os.environ.get("DATA_DIR", "./data")
_prg_cache: dict[str, PRGQuery] = {}
def get_prg(comune: str) -> PRGQuery:
    key = comune.upper().strip()
    if key not in _prg_cache:
        comune_dir = os.path.join(DATA_DIR, key)
        shp_file = os.path.join(comune_dir, "dest_uso_polyg.shp")
        if not os.path.exists(shp_file):
            raise HTTPException(status_code=404,
                detail=f"Shapefile PRG non disponibile per \'{key}\'.")
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
            "data_dir": DATA_DIR, "version": "1.2.0"}
@app.get("/debug")
def debug():
    data_ale = os.path.join(DATA_DIR, "ALESSANDRIA")
    chunks_dir = "/app/data_chunks"
    chunks = sorted(glob.glob(f"{chunks_dir}/chunk_*"))
    total_chunks_size = sum(os.path.getsize(c) for c in chunks)
    return {
        "shp_exists": os.path.exists(os.path.join(data_ale, "dest_uso_polyg.shp")),
        "alessandria_files": sorted(os.listdir(data_ale)) if os.path.exists(data_ale) else [],
        "chunks_count": len(chunks),
        "total_chunks_mb": round(total_chunks_size / 1024 / 1024, 1),
        "version": "1.2.0"
    }
@app.get("/comuni")
def list_comuni():
    if not os.path.exists(DATA_DIR):
        return {"comuni": []}
    comuni = []
    for entry in os.listdir(DATA_DIR):
        ep = os.path.join(DATA_DIR, entry)
        if os.path.isdir(ep):
            comuni.append({"comune": entry,
                "shapefile_disponibile": os.path.exists(os.path.join(ep, "dest_uso_polyg.shp")),
                "in_cache": entry in _prg_cache})
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
