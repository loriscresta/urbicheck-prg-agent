"""
PRGQuery — logica di query spaziale sui shapefile PRG Piemonte
"""

import os
import logging
from typing import Optional
from functools import lru_cache

import shapefile
from pyproj import Transformer
from shapely.geometry import Point, shape
from shapely.strtree import STRtree

logger = logging.getLogger(__name__)

# Proiezione shapefile Piemonte: WGS84 UTM Zone 32N
TRANSFORMER = Transformer.from_crs("EPSG:4326", "EPSG:32632", always_xy=True)

# Layer da interrogare e relative configurazioni
LAYERS = {
    "dest_uso_polyg": {
        "desc": "Destinazione d'uso (layer principale)",
        "fields_map": {
            "DESTINAZIO": "destinazione",
            "COMPROMISS": "compromissione",
            "CARATTERIS": "caratteristica",
            "SIGLA_DI_P": "sigla_piano",
            "AMBITO_TER": "ambito",
            "SHAPE_AREA": "area_mq"
        }
    },
    "vincoli": {
        "desc": "Vincoli PRG",
        "fields_map": {
            "CODICE_VIN": "codice",
            "DECODIFICA": "descrizione",
            "SHAPE_AREA": "area_mq"
        }
    },
    "mod_intervento": {
        "desc": "Modalità di intervento",
        "fields_map": {
            "CODICE_MOD": "codice",
            "CODICE_TIP": "tipo",
            "DECODIFICA": "descrizione",
            "AMBITO_SUE": "ambito"
        }
    },
    "caratt_storica": {
        "desc": "Caratterizzazione storica",
        "fields_map": {
            "DESTINAZIO": "destinazione",
            "CARATTERIS": "caratteristica",
            "SHAPE_AREA": "area_mq"
        }
    }
}

# Codici vincolo con descrizione leggibile e livello di gravità
VINCOLO_SEVERITY = {
    "F8A": "alto",    # Fascia A PSFF — deflusso piena
    "F8B": "alto",    # Fascia B PSFF — esondazione
    "F8C": "medio",   # Fascia C PSFF — inondazione catastrofica
    "H2A": "alto",    # Inidoneità instabilità versante
    "H2B": "alto",    # Inidoneità processi corsi d'acqua
    "C3A": "alto",    # Classe IIIa — inidoneo nuovi insediamenti
    "C3B": "medio",   # Classe IIIb — idoneità geologica da verificare
    "C3C": "medio",   # Classe IIIc — nuovo impianto + idoneità geologica
    "P20": "alto",    # Vincolo monumentale/archeologico L.1089/39
    "P10": "medio",   # Vincolo paesaggistico L.1497/39
    "P30": "medio",   # Vincolo L.431/85
    "Q30": "info",    # Sito archeologico di piano
    "F10": "medio",   # Vincolo idrogeologico
    "A1C": "basso",   # Fascia ferroviaria
    "A1B": "basso",   # Fascia stradale
    "A1A": "basso",   # Fascia cimiteriale
    "B60": "alto",    # Inedificabilità generica
}


class PRGQuery:
    """
    Wrapper per query spaziali sui shapefile PRG di un comune piemontese.
    Carica i geometrie in memoria con STRtree per performance.
    """

    def __init__(self, comune_dir: str):
        self.comune_dir = comune_dir
        self.comune = os.path.basename(comune_dir).upper()
        self._layers: dict = {}
        self._trees: dict = {}
        self._load_all()

    def _load_layer(self, name: str) -> Optional[tuple]:
        """Carica un layer shapefile in memoria. Restituisce (geometrie, record, fields)."""
        shp_path = os.path.join(self.comune_dir, f"{name}.shp")
        if not os.path.exists(shp_path):
            logger.warning(f"Layer {name} non trovato in {self.comune_dir}")
            return None

        sf = shapefile.Reader(shp_path, encoding='latin-1')
        fields = [f[0] for f in sf.fields[1:]]
        geometries = []
        records = []

        for sr in sf.iterShapeRecords():
            try:
                geom = shape(sr.shape.__geo_interface__)
                if not geom.is_valid:
                    geom = geom.buffer(0)  # fix geometrie invalide
                rec = dict(zip(fields, sr.record))
                geometries.append(geom)
                records.append(rec)
            except Exception as e:
                logger.debug(f"Feature ignorata in {name}: {e}")

        logger.info(f"  {name}: {len(geometries)} feature caricate")
        return geometries, records

    def _load_all(self):
        """Carica tutti i layer e costruisce gli STRtree per spatial indexing."""
        logger.info(f"Caricamento PRG per {self.comune}...")
        for layer_name in LAYERS:
            result = self._load_layer(layer_name)
            if result:
                geometries, records = result
                self._layers[layer_name] = (geometries, records)
                # STRtree per query spaziali veloci
                self._trees[layer_name] = STRtree(geometries)
        logger.info(f"PRG {self.comune} pronto.")

    def feature_count(self) -> dict:
        return {name: len(self._layers[name][0]) for name in self._layers}

    def metadata(self) -> dict:
        counts = self.feature_count()
        return {
            "comune": self.comune,
            "layers": counts,
            "dir": self.comune_dir,
            "dest_uso_polyg_total": counts.get("dest_uso_polyg", 0),
            "vincoli_total": counts.get("vincoli", 0),
        }

    def _clean_val(self, val) -> str:
        """Pulisce un valore dal DBF."""
        if val is None:
            return ""
        s = str(val).strip()
        if s in ("None", "0", "0.0"):
            return ""
        return s

    def _rec_to_dict(self, rec: dict, fields_map: dict) -> dict:
        """Converte un record DBF in dict usando il mapping dei campi."""
        out = {}
        for dbf_field, json_field in fields_map.items():
            val = self._clean_val(rec.get(dbf_field, ""))
            if json_field == "area_mq" and val:
                try:
                    val = round(float(val))
                except:
                    pass
            out[json_field] = val
        return out

    def query(self, lat: float, lon: float, buffer_m: float = 5.0) -> dict:
        """
        Query spaziale principale: dato lat/lon WGS84, restituisce tutti i dati PRG.
        """
        x, y = TRANSFORMER.transform(lon, lat)
        point = Point(x, y)

        result = {
            "comune": self.comune,
            "coordinate": {
                "lat": lat,
                "lon": lon,
                "utm_x": round(x, 2),
                "utm_y": round(y, 2)
            },
            "zona_urbanistica": None,
            "vincoli": [],
            "mod_intervento": [],
            "caratt_storica": [],
            "fonte": "Mosaicatura PRG — Regione Piemonte (shapefile BDTRE)",
            "note": None
        }

        # 1. Zona urbanistica
        zona = self._query_single(
            "dest_uso_polyg", point, buffer_m,
            LAYERS["dest_uso_polyg"]["fields_map"]
        )
        if zona:
            result["zona_urbanistica"] = zona

        # 2. Vincoli (tutti i poligoni che contengono il punto)
        vincoli = self._query_multiple(
            "vincoli", point, buffer_m=2.0,
            fields_map=LAYERS["vincoli"]["fields_map"]
        )
        # Arricchisci con severity
        for v in vincoli:
            codice = v.get("codice", "")
            v["gravita"] = VINCOLO_SEVERITY.get(codice, "info")
        result["vincoli"] = sorted(vincoli, key=lambda v: {"alto": 0, "medio": 1, "basso": 2, "info": 3}.get(v.get("gravita","info"), 4))

        # 3. Modalità intervento
        mod = self._query_multiple(
            "mod_intervento", point, buffer_m=buffer_m,
            fields_map=LAYERS["mod_intervento"]["fields_map"]
        )
        result["mod_intervento"] = mod

        # 4. Caratterizzazione storica
        storica = self._query_multiple(
            "caratt_storica", point, buffer_m=buffer_m,
            fields_map=LAYERS["caratt_storica"]["fields_map"]
        )
        result["caratt_storica"] = storica

        # Note
        if not result["zona_urbanistica"]:
            result["note"] = f"Punto non coperto dal PRG vigente — buffer {buffer_m}m"

        return result

    def _query_single(self, layer_name: str, point: Point, buffer_m: float, fields_map: dict) -> Optional[dict]:
        """Trova il poligono che contiene il punto (con fallback al più vicino entro buffer)."""
        if layer_name not in self._layers:
            return None

        geometries, records = self._layers[layer_name]
        tree = self._trees[layer_name]

        # Prima: exact contains (fast with STRtree candidate check)
        candidates = tree.query(point)
        for idx in candidates:
            if geometries[idx].contains(point):
                rec = self._rec_to_dict(records[idx], fields_map)
                return rec

        # Fallback: nearest entro buffer_m
        if buffer_m > 0:
            buf = point.buffer(buffer_m)
            candidates = tree.query(buf)
            best_idx = None
            best_dist = float('inf')
            for idx in candidates:
                d = geometries[idx].distance(point)
                if d < best_dist:
                    best_dist = d
                    best_idx = idx
            if best_idx is not None and best_dist <= buffer_m:
                rec = self._rec_to_dict(records[best_idx], fields_map)
                rec["distanza_bordo_m"] = round(best_dist, 1)
                return rec

        return None

    def _query_multiple(self, layer_name: str, point: Point, buffer_m: float, fields_map: dict) -> list:
        """Trova tutti i poligoni che contengono il punto."""
        if layer_name not in self._layers:
            return []

        geometries, records = self._layers[layer_name]
        tree = self._trees[layer_name]

        results = []
        buf = point.buffer(max(buffer_m, 2.0))
        candidates = tree.query(buf)

        seen = set()
        for idx in candidates:
            try:
                if geometries[idx].contains(point) or geometries[idx].distance(point) < 2.0:
                    rec = self._rec_to_dict(records[idx], fields_map)
                    key = rec.get("codice", "") or rec.get("destinazione", "") + rec.get("caratteristica", "")
                    if key not in seen:
                        seen.add(key)
                        results.append(rec)
            except:
                pass

        return results
