FROM python:3.11-slim

WORKDIR /app

# Dipendenze sistema
RUN apt-get update && apt-get install -y \
    libgeos-dev \
    libproj-dev \
    curl \
    unzip \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN chmod +x /app/entrypoint.sh

ENV DATA_DIR=/app/data
ENV PORT=8000

EXPOSE 8000

CMD ["/app/entrypoint.sh"]
