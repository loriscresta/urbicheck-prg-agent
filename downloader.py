"""
downloader.py — scarica shapefile PRG dal Geoportale Piemonte
URL pattern per comune: ricerca per nome sul catalogo WFS/WMS Piemonte
"""

import os
import zipfile
import logging
import urllib.request
import urllib.parse

logger = logging.getLogger(__name__)

# URL base del servizio WFS Piemonte per download shapefile PRG
# La Mosaicatura PRG è disponibile su:
# https://www.geoportale.piemonte.it/geonetwork/srv/ita/catalog.search#/search?any=mosaicatura+PRG
#
# Il download diretto usa questo pattern (aggiornare se cambia):
GEOPORTALE_DOWNLOAD_BASE = (
    "https://geomap.reteunitaria.piemonte.it/"
    "ws/taims/rp-01/taims/getShapeFile?"
    "LAYER=PRG_MOSAICATURA&COMUNE={comune_upper}&TIPO=SHP"
)

# Comuni con URL specifici (fallback manuali)
MANUAL_URLS = {
    "TORINO": None,  # Da configurare
    "ALESSANDRIA": None,  # Già presente nel repo
}


def ensure_shapefile(comune: str, data_dir: str) -> bool:
    """
    Verifica che lo shapefile per il comune sia presente.
    Se non lo è, tenta il download dal Geoportale Piemonte.

    Returns: True se lo shapefile è disponibile, False altrimenti
    """
    comune_upper = comune.upper().strip()
    target_dir = os.path.join(data_dir, comune_upper)
    shp_file = os.path.join(target_dir, "dest_uso_polyg.shp")

    if os.path.exists(shp_file):
        logger.info(f"Shapefile {comune_upper} già presente")
        return True

    # Tenta download
    logger.info(f"Download shapefile PRG per {comune_upper}...")
    os.makedirs(target_dir, exist_ok=True)

    url = GEOPORTALE_DOWNLOAD_BASE.format(comune_upper=urllib.parse.quote(comune_upper))
    zip_path = os.path.join(target_dir, f"{comune_upper}_prg.zip")

    try:
        urllib.request.urlretrieve(url, zip_path)

        with zipfile.ZipFile(zip_path, 'r') as zf:
            # Estrai e appiattisci la struttura directory
            for member in zf.namelist():
                filename = os.path.basename(member)
                if filename and not member.endswith('/'):
                    ext = os.path.splitext(filename)[1].lower()
                    if ext in ('.shp', '.dbf', '.prj', '.shx'):
                        with zf.open(member) as src, open(os.path.join(target_dir, filename), 'wb') as dst:
                            dst.write(src.read())

        os.remove(zip_path)

        if os.path.exists(shp_file):
            logger.info(f"Shapefile {comune_upper} scaricato con successo")
            return True
        else:
            logger.error(f"ZIP scaricato ma dest_uso_polyg.shp non trovato per {comune_upper}")
            return False

    except Exception as e:
        logger.error(f"Download fallito per {comune_upper}: {e}")
        logger.info(
            f"Download manuale: scarica il ZIP del PRG di {comune_upper} da "
            f"https://www.geoportale.piemonte.it e posizionalo in data/{comune_upper}/"
        )
        # Pulisci directory vuota
        try:
            if os.path.exists(zip_path):
                os.remove(zip_path)
            if not os.listdir(target_dir):
                os.rmdir(target_dir)
        except:
            pass
        return False
