# SETUP.ps1 — Crea repo GitHub e fa il primo push del PRG Agent
# Esegui da PowerShell nella cartella prg-agent:
#   cd "C:\Users\info\AppData\...\outputs\prg-agent"
#   .\SETUP.ps1

Write-Host "=== PRG Agent — Setup GitHub ===" -ForegroundColor Cyan

# 1. Chiedi GitHub token
Write-Host ""
Write-Host "Hai bisogno di un GitHub Personal Access Token (classic)." -ForegroundColor Yellow
Write-Host "Crealo su: https://github.com/settings/tokens/new" -ForegroundColor Yellow
Write-Host "Scopes necessari: repo (full)" -ForegroundColor Yellow
Write-Host ""
$token = Read-Host "Incolla il tuo GitHub Token"
$username = Read-Host "Il tuo username GitHub"

# 2. Crea repo su GitHub via API
Write-Host "`nCreazione repo GitHub..." -ForegroundColor Cyan
$headers = @{
    Authorization = "token $token"
    Accept        = "application/vnd.github.v3+json"
}
$body = @{
    name        = "urbicheck-prg-agent"
    description = "Microservizio per query spaziali sul PRG Piemonte — Urbicheck"
    private     = $false
    auto_init   = $false
} | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Uri "https://api.github.com/user/repos" `
        -Method POST -Headers $headers -Body $body -ContentType "application/json"
    Write-Host "Repo creato: $($response.html_url)" -ForegroundColor Green
    $repoUrl = "https://${username}:${token}@github.com/${username}/urbicheck-prg-agent.git"
} catch {
    Write-Host "ERRORE creazione repo: $_" -ForegroundColor Red
    Write-Host "Forse esiste già. Continuo con push..." -ForegroundColor Yellow
    $repoUrl = "https://${username}:${token}@github.com/${username}/urbicheck-prg-agent.git"
}

# 3. Inizializza git locale
Write-Host "`nInizializzazione git locale..." -ForegroundColor Cyan
git init
git config user.email "loris.cresta@gmail.com"
git config user.name "Loris Cresta"
git branch -M main

# 4. Aggiungi file
Write-Host "Aggiunta file codice..." -ForegroundColor Cyan
git add main.py prg_query.py downloader.py requirements.txt Dockerfile railway.toml README.md SETUP.ps1 .gitignore .gitattributes
git add scripts/

# Aggiungi shapefile Alessandria (tutti i layer — inclusi nell'immagine Docker)
Write-Host "Aggiunta shapefile Alessandria..." -ForegroundColor Cyan
git add -f data/ALESSANDRIA/

git commit -m "Initial commit — PRG Agent Piemonte

- FastAPI microservice for spatial queries on PRG shapefiles
- Alessandria dataset included (dest_uso_polyg, vincoli, mod_intervento)
- STRtree spatial indexing for fast queries
- Base44/Urbicheck integration snippet"

# 5. Push
Write-Host "Push su GitHub..." -ForegroundColor Cyan
git remote add origin $repoUrl
git push -u origin main

Write-Host ""
Write-Host "FATTO! Repo disponibile su:" -ForegroundColor Green
Write-Host "https://github.com/$username/urbicheck-prg-agent" -ForegroundColor Green
Write-Host ""
Write-Host "=== PROSSIMO STEP: Deploy su Railway ===" -ForegroundColor Cyan
Write-Host "1. Vai su https://railway.app" -ForegroundColor White
Write-Host "2. New Project → Deploy from GitHub repo" -ForegroundColor White
Write-Host "3. Seleziona 'urbicheck-prg-agent'" -ForegroundColor White
Write-Host "4. Railway legge il Dockerfile e fa il deploy automatico" -ForegroundColor White
Write-Host "5. Ottieni URL tipo: https://prg-agent-xxx.up.railway.app" -ForegroundColor White
Write-Host ""
Write-Host "Poi in Base44: imposta env var PRG_AGENT_URL = [url railway]" -ForegroundColor Yellow
