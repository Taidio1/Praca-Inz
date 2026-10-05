@echo off
title OPES Launcher
echo ==================================================
echo        Uruchamianie aplikacji OPES
echo ==================================================

set SCRIPT_DIR=%~dp0

echo.
echo [1/3] Uruchamianie Backendu (FastAPI na http://localhost:8000)...
start "OPES Backend" cmd /k "cd /d "%SCRIPT_DIR%backend" && (if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat) && python -m uvicorn src.dashboard.api:app --reload --port 8000"

echo [2/3] Uruchamianie silnika informacyjnego (worker newsow)...
start "OPES Engine" cmd /k "cd /d "%SCRIPT_DIR%backend" && (if exist .venv\Scripts\activate.bat call .venv\Scripts\activate.bat) && python -m src.engine.runner"

echo [3/3] Uruchamianie Frontendu (Next.js na http://localhost:3000)...
start "OPES Frontend" cmd /k "cd /d "%SCRIPT_DIR%frontend" && npm run dev"

echo.
echo ==================================================
echo   Backend i Frontend zostały uruchomione w osobnych oknach!
echo   - Frontend UI:  http://localhost:3000
echo   - Backend API:  http://localhost:8000
echo   - API Docs:     http://localhost:8000/docs
echo ==================================================
echo.
