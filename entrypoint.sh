#!/bin/bash
set -e

SHP="/app/data/ALESSANDRIA/dest_uso_polyg.shp"
if [ ! -f "$SHP" ]; then
    echo "=== Assemblaggio shapefile Alessandria da chunk ==="
    mkdir -p /app/data/ALESSANDRIA
    
    # Riassembla i 14 chunk in un unico ZIP
    cat /app/data_chunks/chunk_* > /tmp/alessandria.zip
    
    FILESIZE=$(stat -c%s /tmp/alessandria.zip)
    echo "ZIP assemblato: ${FILESIZE} bytes"
    
    unzip -o /tmp/alessandria.zip -d /app/data/ALESSANDRIA/
    rm /tmp/alessandria.zip
    
    echo "Shapefile pronti: $(ls /app/data/ALESSANDRIA/*.shp | wc -l) layer"
fi

exec python main.py
