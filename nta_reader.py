"""
nta_reader.py — Lettore NTA (Norme Tecniche di Attuazione) per Urbicheck / prg-agent

Legge i dati NTA estratti dai PDF comunali e li serve via API:
  - parametri strutturati per zona (JSON)  -> alimenta la scheda "cosa posso fare"
  - ricerca semantica sul testo NTA (RAG)   -> risposta con citazione dell'articolo
  - match destinazione shapefile -> zona    -> chiude la catena particella->zona->regole

Dati attesi in:  {DATA_DIR}/{COMUNE}/nta_zones.json
                 {DATA_DIR}/{COMUNE}/nta_articles.json
                 {DATA_DIR}/{COMUNE}/nta_chunks.json

Il RAG usa un BM25 puro-python (nessuna dipendenza esterna). Se la variabile
d'ambiente ANTHROPIC_API_KEY e' presente, /nta/query sintetizza anche una
risposta in linguaggio naturale citando gli articoli; altrimenti restituisce
i passaggi rilevanti con i riferimenti.
"""

import os, re, json, math, unicodedata, logging
from collections import Counter
from typing import Optional
from functools import lru_cache

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

logger = logging.getLogger("nta_reader")
DATA_DIR = os.environ.get("DATA_DIR", "./data")

router = APIRouter(prefix="/nta", tags=["NTA"])

_STOP = set("""a al alla alle allo ai agli e ed o od di del dei della delle degli da
dal in nel nella nelle con su per tra fra il lo la i gli le un uno una che chi cui non
sono essere come anche ove salvo sensi comma articolo art dell""".split())

def _norm(s):
    s = unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode()
    return s.lower()

def _tok(s):
    return [t for t in re.findall(r"[a-z0-9]+", _norm(s)) if len(t) > 2 and t not in _STOP]

def _artkey(s):
    k = re.sub(r'[^a-z0-9]', '', _norm(s).replace('articolo','art'))
    if not k.startswith('art'): k = 'art' + k
    return k

class BM25:
    def __init__(self, docs, k1=1.5, b=0.75):
        self.docs = docs; self.k1, self.b = k1, b
        self.N = len(docs); self.dl = [len(d) for d in docs]
        self.avgdl = (sum(self.dl) / self.N) if self.N else 0
        self.tf = [Counter(d) for d in docs]
        df = Counter()
        for d in docs:
            for t in set(d): df[t] += 1
        self.idf = {t: math.log(1 + (self.N - n + 0.5) / (n + 0.5)) for t, n in df.items()}
    def score(self, q, i):
        s = 0.0; tf = self.tf[i]
        for t in q:
            if t not in tf: continue
            f = tf[t]
            s += self.idf.get(t, 0) * (f * (self.k1 + 1)) / (f + self.k1 * (1 - self.b + self.b * self.dl[i] / (self.avgdl or 1)))
        return s
    def topn(self, q, n=5):
        sc = [(self.score(q, i), i) for i in range(self.N)]
        sc = [x for x in sc if x[0] > 0]; sc.sort(reverse=True)
        return sc[:n]

class NTAComune:
    def __init__(self, comune_dir):
        self.dir = comune_dir
        self.comune = os.path.basename(comune_dir).upper()
        self.zones = json.load(open(os.path.join(comune_dir, "nta_zones.json"), encoding="utf-8"))
        self.articles = json.load(open(os.path.join(comune_dir, "nta_articles.json"), encoding="utf-8"))
        self.chunks = json.load(open(os.path.join(comune_dir, "nta_chunks.json"), encoding="utf-8"))
        self._bm25 = BM25([_tok(c["testo"]) for c in self.chunks])
        self._by_art = {_artkey(z["articolo"]): z for z in self.zones["zone"]}
        self._by_name = {_norm(z["nome"]): z for z in self.zones["zone"]}
    def get_zona(self, key):
        return self._by_art.get(_artkey(key))
    def match_destinazione(self, destinazione):
        q = _norm(destinazione)
        if not q: return None
        if q in self._by_name: return self._by_name[q]
        qt = set(_tok(destinazione)); best, bs = None, 0.0
        for z in self.zones["zone"]:
            zt = set(_tok(z["nome"]))
            if not zt: continue
            score = len(qt & zt) / (len(zt) ** 0.5)
            if score > bs: best, bs = z, score
        return best if bs >= 1.0 else None
    def query_rag(self, domanda, n=5):
        out = []
        for score, i in self._bm25.topn(_tok(domanda), n):
            c = self.chunks[i]
            out.append({"articolo": c["articolo"], "titolo": c["titolo"],
                        "score": round(score, 3), "testo": c["testo"]})
        return out

@lru_cache(maxsize=32)
def get_comune(comune):
    key = comune.upper().strip()
    cdir = os.path.join(DATA_DIR, key)
    if not os.path.exists(os.path.join(cdir, "nta_zones.json")):
        raise HTTPException(404, f"NTA non disponibili per '{key}'.")
    return NTAComune(cdir)

def _ai_answer(domanda, passaggi):
    key = os.environ.get("ANTHROPIC_API_KEY")
    if not key: return None
    try:
        import httpx
        contesto = "\n\n".join(f"[{p['articolo']} - {p['titolo']}]\n{p['testo']}" for p in passaggi)
        r = httpx.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.environ.get("NTA_CLAUDE_MODEL", "claude-sonnet-4-6"), "max_tokens": 700,
                  "system": ("Sei un assistente urbanistico. Rispondi SOLO in base agli estratti NTA forniti, "
                             "citando sempre l'articolo tra parentesi. Se l'informazione non c'e', dillo. Sii conciso."),
                  "messages": [{"role": "user", "content": f"Domanda: {domanda}\n\nEstratti NTA:\n{contesto}"}]},
            timeout=30)
        r.raise_for_status()
        return r.json()["content"][0]["text"]
    except Exception as e:
        logger.warning(f"AI answer skip: {e}"); return None

class QueryNTA(BaseModel):
    comune: str; domanda: str; n: Optional[int] = 5; ai: Optional[bool] = True
class MatchNTA(BaseModel):
    comune: str; destinazione: str

@router.get("/comuni")
def nta_comuni():
    out = []
    if os.path.exists(DATA_DIR):
        for entry in os.listdir(DATA_DIR):
            if os.path.exists(os.path.join(DATA_DIR, entry, "nta_zones.json")): out.append(entry)
    return {"comuni": out, "totale": len(out)}

@router.get("/{comune}/zone")
def nta_zone(comune: str):
    c = get_comune(comune)
    return {"comune": c.comune, "strumento": c.zones.get("strumento"), "fonte": c.zones.get("fonte_url"),
            "zone": [{"articolo": z["articolo"], "nome": z["nome"], "categoria": z["categoria"]} for z in c.zones["zone"]]}

@router.get("/{comune}/zona/{articolo}")
def nta_zona(comune: str, articolo: str):
    z = get_comune(comune).get_zona(articolo)
    if not z: raise HTTPException(404, f"Zona '{articolo}' non trovata per {comune}.")
    return z

@router.post("/match")
def nta_match(req: MatchNTA):
    c = get_comune(req.comune); z = c.match_destinazione(req.destinazione)
    return {"comune": c.comune, "destinazione_input": req.destinazione, "match": z, "trovato": z is not None}

@router.post("/query")
def nta_query(req: QueryNTA):
    c = get_comune(req.comune); passaggi = c.query_rag(req.domanda, req.n or 5)
    if not passaggi:
        return {"comune": c.comune, "domanda": req.domanda, "risposta": None, "passaggi": [], "nota": "Nessun passaggio rilevante."}
    risposta = _ai_answer(req.domanda, passaggi) if req.ai else None
    return {"comune": c.comune, "domanda": req.domanda, "risposta": risposta,
            "citazioni": sorted({p["articolo"] for p in passaggi}), "passaggi": passaggi}
