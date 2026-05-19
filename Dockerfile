FROM python:3.11-slim

WORKDIR /app

# Dipendenze sistema per pyproj/shapely + curl per download dati
RUN apt-get update && apt-get install -y \
    libgeos-dev \
    libproj-dev \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Download shapefile Alessandria da GitHub Releases (baked nell'immagine)
RUN mkdir -p /app/data/ALESSANDRIA && \
    curl -L "https://github.com/loriscresta/urbicheck-prg-agent/releases/download/v1.0.0-data/alessandria_prg.zip" \
    -o /tmp/alessandria.zip && \
    unzip /tmp/alessandria.zip -d /app/data/ALESSANDRIA/ && \
    rm /tmp/alessandria.zip && \
    echo "Shapefile Alessandria OK:" && ls /app/data/ALESSANDRIA/*.shp

ENV DATA_DIR=/app/data
ENV PORT=8000

EXPOSE 8000

CMD ["python", "main.py"]
