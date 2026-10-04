# Demo bootstrap: seed data + start API (frontend separately with npm run dev)
$ErrorActionPreference = "Stop"
Set-Location "$PSScriptRoot\..\backend"
if (-not (Test-Path .venv)) {
  python -m venv .venv
  .\.venv\Scripts\pip install -r requirements.txt
}
.\.venv\Scripts\python -m app.scripts.seed_demo
Write-Host "API: http://127.0.0.1:8000/docs"
Write-Host "UI:  cd frontend && npm run dev -> http://127.0.0.1:5173"
.\.venv\Scripts\uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
