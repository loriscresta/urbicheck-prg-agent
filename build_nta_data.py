"""
build_nta_data.py — Pipeline riproducibile: PDF NTA comunale -> dati per nta_reader

Passi:
  1. scarica il PDF (URL) o usa un file locale
  2. estrae il testo (PyMuPDF) con rilevazione scansione (fallback OCR opzionale)
  3. spezza in articoli (deterministico) -> nta_articles.json
  4. crea i chunk RAG -> nta_chunks.json
  5. (opzionale, se ANTHROPIC_API_KEY) estrae i parametri per zona -> nta_zones.json

Uso:
  python build_nta_data.py --comune ALESSANDRIA --istat 006003 \
      --url "https://.../getfile.aspx?ref=531" --out data/ALESSANDRIA
  python build_nta_data.py --comune X --pdf norme.pdf --out data/X --zones-ai
"""
import os, re, json, math, argparse, hashlib, unicodedata, urllib.request

def norm_ws(s): return re.sub(r'[ \t]+', ' ', s).strip()

def download(url, dest):
    req = urllib.request.Request(url, headers={"User-Agent": "UrbiCheck/1.0 (info@urbicheck.it)"})
    with urllib.request.urlopen(req, timeout=120) as r, open(dest, "wb") as f:
        f.write(r.read())
    return dest

def extract_text(pdf_path, ocr=False):
    import fitz
    d = fitz.open(pdf_path)
    pages = [p.get_text() for p in d]
    full = "\n".join(pages)
    empty = sum(1 for t in pages if len(t.strip()) < 20)
    scanned = empty > len(pages) * 0.4
    if scanned and ocr:
        import pytesseract
        from PIL import Image
        import io
        pages = []
        for p in d:
            pix = p.get_pixmap(dpi=300)
            img = Image.open(io.BytesIO(pix.tobytes("png")))
            pages.append(pytesseract.image_to_string(img, lang="ita"))
        full = "\n".join(pages)
    return full, {"pagine": d.page_count, "scansionato": scanned}

def split_articles(full, min_body=40):
    hpat = re.compile(r'(?m)^\s*(?:Articolo|Art\.?)\s*(\d+)\s*(bis|ter|quater|quinquies|sexies|septies)?\b')
    matches = list(hpat.finditer(full))
    best = {}
    for i, m in enumerate(matches):
        num, suf = int(m.group(1)), (m.group(2) or "")
        start = m.start()
        end = matches[i+1].start() if i+1 < len(matches) else len(full)
        body = full[start:end].strip()
        k = (num, suf)
        if k not in best or len(body) > len(best[k]):
            best[k] = body
    arts = []
    for (num, suf), body in sorted(best.items()):
        if len(body) < min_body:
            continue
        head = body.split("\n", 1)
        head = head[0] if isinstance(head, list) else head
        m = re.match(r'(?:Articolo|Art\.?)\s*\d+\s*(?:bis|ter|quater|quinquies|sexies|septies)?\s*[-:.)]*\s*(.*)', head, re.I)
        titolo = (m.group(1).strip() if m and m.group(1).strip() else (body.split("\n")[1].strip() if len(body.split("\n")) > 1 else ""))
        code = f"Art. {num}" + (f" {suf}" if suf else "")
        arts.append({"codice": code, "num": num, "suf": suf,
                     "titolo": norm_ws(titolo)[:120], "testo": norm_ws(body.replace("\n", " "))})
    arts.sort(key=lambda a: (a["num"], a["suf"]))
    return arts

def make_chunks(arts, size=1200, overlap=200):
    chunks = []
    for a in arts:
        t = a["testo"]; i = 0; j = 0
        while i < len(t):
            ch = t[i:i+size]
            cid = hashlib.md5((a["codice"]+str(j)).encode()).hexdigest()[:10]
            chunks.append({"chunk_id": cid, "articolo": a["codice"], "titolo": a["titolo"], "parte": j, "testo": ch})
            i += size - overlap; j += 1
    return chunks

def extract_zones_ai(arts, comune, istat, meta):
    """Estrae i parametri per zona via Claude API. Richiede ANTHROPIC_API_KEY."""
    import httpx
    key = os.environ["ANTHROPIC_API_KEY"]
    # candidate: articoli il cui titolo inizia con 'Aree'/'Area'/'Nuclei' (zone edificabili)
    cand = [a for a in arts if re.match(r'(aree|area|nuclei)\b', a["titolo"], re.I)]
    zone = []
    schema = ('{"nome":str,"categoria":"residenziale|produttivo|commerciale|direzionale|turistico|agricolo|servizi|altro",'
              '"destinazioni_ammesse":[str],"parametri":{"indice_fabbric_fondiario_If":{"valore":num,"unita":"mc/mq"}|null,'
              '"indice_util_territoriale_Ut":{"valore":num,"unita":"mq/mq"}|null,"indice_util_fondiaria_Uf":{"valore":num,"unita":"mq/mq"}|null,'
              '"altezza_max_m":num|null,"rapporto_copertura_max_pct":num|null,"distanza_min_confini_m":num|null,"distanza_min_strade_m":num|null},'
              '"modalita_intervento":str,"note":str}')
    for a in cand:
        r = httpx.post("https://api.anthropic.com/v1/messages",
            headers={"x-api-key": key, "anthropic-version": "2023-06-01", "content-type": "application/json"},
            json={"model": os.environ.get("NTA_CLAUDE_MODEL", "claude-sonnet-4-6"), "max_tokens": 900,
                  "system": ("Estrai i parametri urbanistici della zona dall'articolo NTA. "
                             "Rispondi SOLO con un JSON valido secondo lo schema. Metti null dove il valore non e' indicato. "
                             "Non inventare numeri."),
                  "messages": [{"role": "user", "content": f"Schema: {schema}\n\nArticolo {a['codice']} - {a['titolo']}:\n{a['testo'][:6000]}"}]},
            timeout=40)
        r.raise_for_status()
        txt = r.json()["content"][0]["text"]
        mjson = re.search(r'\{.*\}', txt, re.S)
        if not mjson: continue
        try: z = json.loads(mjson.group())
        except Exception: continue
        z["articolo"] = a["codice"]; z["riferimento"] = f"NTA {comune.title()} - {a['codice']}"
        zone.append(z)
    return {"comune": comune.title(), "istat": istat, "n_zone": len(zone), "zone": zone, **meta}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--comune", required=True)
    ap.add_argument("--istat", default="")
    ap.add_argument("--url"); ap.add_argument("--pdf")
    ap.add_argument("--out", required=True)
    ap.add_argument("--ocr", action="store_true")
    ap.add_argument("--zones-ai", action="store_true")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    pdf = a.pdf or download(a.url, os.path.join(a.out, "nta_source.pdf"))
    full, meta = extract_text(pdf, ocr=a.ocr)
    arts = split_articles(full)
    chunks = make_chunks(arts)
    json.dump(arts, open(os.path.join(a.out, "nta_articles.json"), "w"), ensure_ascii=False, indent=1)
    json.dump(chunks, open(os.path.join(a.out, "nta_chunks.json"), "w"), ensure_ascii=False, indent=1)
    print(f"[{a.comune}] pagine={meta['pagine']} scansionato={meta['scansionato']} articoli={len(arts)} chunk={len(chunks)}")
    if a.zones_ai:
        zones = extract_zones_ai(arts, a.comune, a.istat,
                                 {"strumento": "PRGC/NTA", "fonte_url": a.url or a.pdf})
        json.dump(zones, open(os.path.join(a.out, "nta_zones.json"), "w"), ensure_ascii=False, indent=1)
        print(f"[{a.comune}] zone strutturate (AI)={zones['n_zone']}")
    else:
        print("NB: nta_zones.json non generato (usa --zones-ai con ANTHROPIC_API_KEY, o fornisci il file a mano).")

if __name__ == "__main__":
    main()
