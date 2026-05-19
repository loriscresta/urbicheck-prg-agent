FROM python:3.11-slim

WORKDIR /app

# Dipendenze sistema per pyproj/shapely
RUN apt-get update && apt-get install -y \
    libgeos-dev \
    libproj-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# La cartella data/ contiene gli shapefile dei comuni
# Può essere montata come volume in produzione
ENV DATA_DIR=/app/data
ENV PORT=8000

EXPOSE 8000

CMD ["python", "main.py"]
