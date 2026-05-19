# PRG Agent — Piemonte Urbanistic Query Microservice

Microservizio per query spaziali sul **Piano Regolatore Generale (PRG)** dei comuni piemontesi.
Usa la Mosaicatura PRG della Regione Piemonte (shapefile BDTRE).

## Cosa restituisce

Per ogni coppia lat/lon + comune:
- **Zona urbanistica**: destinazione d'uso, compromissione, caratteristica (es. "Centro storico di valore storico-artistico")
- **Vincoli PRG**: con codice e gravità (es. F8C = fascia inondazione, Q30 = sito archeologico)
- **Modalità di intervento**: tipo di piano attuativo richiesto
- **Caratterizzazione storica**

## Deploy rapido (Railway)

1. Fork questo repo
2. Vai su [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Seleziona `urbicheck-prg-agent`
4. Railway fa tutto automaticamente — ottieni URL tipo `prg-agent-xxx.railway.app`

## API

```bash
# Health check
GET /health

# Query zona PRG
POST /query
{
  "comune": "alessandria",
  "lat": 44.91881,
  "lon": 8.61368
}
```

## Aggiunta di nuovi comuni

1. Scarica il ZIP del PRG dal [Geoportale Piemonte](https://www.geoportale.piemonte.it)
2. Estrai in `data/NOME_COMUNE/`
3. Il servizio caricherà automaticamente il nuovo comune

## Integrazione con Base44/Urbicheck

Vedi `scripts/call_from_base44.ts` per lo snippet da incollare in `wfsLiguria/entry.ts`.
Imposta env var `PRG_AGENT_URL` in Base44 con l'URL Railway del servizio.
