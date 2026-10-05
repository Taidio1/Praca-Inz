# ==========================================
# OPES Launcher for PowerShell
# ==========================================

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition

Write-Host "==================================================" -ForegroundColor Cyan
Write-Host "       Uruchamianie aplikacji OPES               " -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Cyan

# 1. Backend
Write-Host "`n[1/3] Uruchamianie Backendu (FastAPI na http://localhost:8000)..." -ForegroundColor Yellow
$backendCmd = "cd /d `"$ScriptDir\backend`" && (if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat) && python -m uvicorn src.dashboard.api:app --reload --port 8000"
Start-Process cmd.exe -ArgumentList "/k", $backendCmd

# 2. Silnik informacyjny (worker newsów)
Write-Host "[2/3] Uruchamianie silnika informacyjnego (worker newsów)..." -ForegroundColor Yellow
$engineCmd = "cd /d `"$ScriptDir\backend`" && (if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat) && python -m src.engine.runner"
Start-Process cmd.exe -ArgumentList "/k", $engineCmd

# 3. Frontend
Write-Host "[3/3] Uruchamianie Frontendu (Next.js na http://localhost:3000)..." -ForegroundColor Yellow
$frontendCmd = "cd /d `"$ScriptDir\frontend`" && npm run dev"
Start-Process cmd.exe -ArgumentList "/k", $frontendCmd

Write-Host "`n==================================================" -ForegroundColor Green
Write-Host "  Aplikacja OPES została uruchomiona!" -ForegroundColor Green
Write-Host "  - Frontend (UI):  http://localhost:3000" -ForegroundColor Cyan
Write-Host "  - Backend (API):  http://localhost:8000" -ForegroundColor Cyan
Write-Host "  - API Docs:       http://localhost:8000/docs" -ForegroundColor Cyan
Write-Host "==================================================" -ForegroundColor Green
