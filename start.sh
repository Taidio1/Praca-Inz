#!/usr/bin/env bash

# ==========================================
# Opes - Skrypt uruchomieniowy całej aplikacji
# ==========================================

# Ścieżka do głównego katalogu projektu
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Kolory w konsoli
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m' # Brak koloru

echo -e "${BLUE}==================================================${NC}"
echo -e "${BLUE}       Uruchamianie aplikacji OPES               ${NC}"
echo -e "${BLUE}==================================================${NC}"

# Funkcja czyszcząca procesy przy zamknięciu (Ctrl+C)
cleanup() {
    echo ""
    echo -e "${YELLOW}Zatrzymywanie wszystkich usług...${NC}"
    
    if [ -n "$BACKEND_PID" ]; then
        echo "Zamykanie backendu (PID: $BACKEND_PID)..."
        kill "$BACKEND_PID" 2>/dev/null
    fi
    
    if [ -n "$ENGINE_PID" ]; then
        echo "Zamykanie silnika informacyjnego (PID: $ENGINE_PID)..."
        kill "$ENGINE_PID" 2>/dev/null
    fi

    if [ -n "$FRONTEND_PID" ]; then
        echo "Zamykanie frontendu (PID: $FRONTEND_PID)..."
        kill "$FRONTEND_PID" 2>/dev/null
    fi

    # Zabić ewentualne procesy potomne w tle
    jobs -p | xargs -r kill 2>/dev/null
    
    echo -e "${GREEN}Aplikacja została zatrzymana.${NC}"
    exit 0
}

# Przechwycenie sygnałów wyjścia
trap cleanup SIGINT SIGTERM EXIT

# 1. Backend (FastAPI)
echo -e "\n${YELLOW}[1/3] Uruchamianie Backendu (FastAPI)...${NC}"
cd "$SCRIPT_DIR/backend" || exit 1

if [ -f "$SCRIPT_DIR/backend/.venv/Scripts/activate" ]; then
    echo "Aktywowanie wirtualnego środowiska Python (.venv Windows)..."
    source "$SCRIPT_DIR/backend/.venv/Scripts/activate"
elif [ -f "$SCRIPT_DIR/backend/.venv/bin/activate" ]; then
    echo "Aktywowanie wirtualnego środowiska Python (.venv Unix)..."
    source "$SCRIPT_DIR/backend/.venv/bin/activate"
fi

python -m uvicorn src.dashboard.api:app --reload --port 8000 &
BACKEND_PID=$!

# 2. Silnik informacyjny (worker newsów)
echo -e "\n${YELLOW}[2/3] Uruchamianie silnika informacyjnego (worker newsów)...${NC}"
python -m src.engine.runner &
ENGINE_PID=$!

# 3. Frontend (Next.js)
echo -e "\n${YELLOW}[3/3] Uruchamianie Frontendu (Next.js)...${NC}"
cd "$SCRIPT_DIR/frontend" || exit 1

if [ ! -d "node_modules" ]; then
    echo "Brak katalogu node_modules. Instalacja zależności npm..."
    npm install
fi

npm run dev &
FRONTEND_PID=$!

# Podsumowanie
echo -e "\n${GREEN}==================================================${NC}"
echo -e "${GREEN}  Aplikacja OPES została uruchomiona!             ${NC}"
echo -e "${GREEN}  - Frontend (UI):  ${BLUE}http://localhost:3000${NC}"
echo -e "${GREEN}  - Backend (API):  ${BLUE}http://localhost:8000${NC}"
echo -e "${GREEN}  - Dokumentacja:   ${BLUE}http://localhost:8000/docs${NC}"
echo -e "${GREEN}==================================================${NC}"
echo -e "${YELLOW}Naciśnij Ctrl+C, aby zatrzymać aplikację.${NC}\n"

# Oczekiwanie na procesy z tła
wait
