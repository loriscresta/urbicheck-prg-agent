#!/bin/bash
set -e

# Scarica shapefile Alessandria se non presente
SHP="/app/data/ALESSANDRIA/dest_uso_polyg.shp"
if [ ! -f "$SHP" ]; then
    echo "Download shapefile Alessandria..."
    mkdir -p /app/data/ALESSANDRIA
    # Usa API GitHub per ottenere URL diretto dell asset
    ASSET_URL=$(curl -sL \
      -H "Accept: application/octet-stream" \
      "https://api.github.com/repos/loriscresta/urbicheck-prg-agent/releases/assets" \
      2>/dev/null || echo "")
    
    # Download diretto con redirect
    curl -L --retry 3 --retry-delay 2 \
      "https://github.com/loriscresta/urbicheck-prg-agent/releases/download/v1.0.0-data/alessandria_prg.zip" \
      -o /tmp/alessandria.zip \
      -H "User-Agent: Mozilla/5.0" \
      --max-time 120
    
    FILESIZE=$(stat -c%s /tmp/alessandria.zip 2>/dev/null || echo 0)
    echo "Downloaded: ${FILESIZE} bytes"
    
    if [ "$FILESIZE" -gt 1000000 ]; then
        unzip -o /tmp/alessandria.zip -d /app/data/ALESSANDRIA/
        rm /tmp/alessandria.zip
        echo "Shapefile OK: $(ls /app/data/ALESSANDRIA/*.shp | wc -l) file shp"
    else
        echo "Download fallito (${FILESIZE} bytes). Avvio senza dati Alessandria."
    fi
fi

exec python main.py
