#!/usr/bin/env bash
# Wdrożenie na serwerze: pobiera najnowszy main i przebudowuje kontenery.
# Uruchamiane przez GitHub Actions (.github/workflows/deploy.yml) po merge'u do main,
# można też odpalić ręcznie na serwerze: ./deploy.sh
set -euo pipefail

BRANCH="${DEPLOY_BRANCH:-main}"
cd "$(dirname "${BASH_SOURCE[0]}")"

echo "==> Pobieranie $BRANCH"
git fetch --prune origin "$BRANCH"
# Pliki .env są poza gitem, więc reset ich nie rusza
git reset --hard "origin/$BRANCH"
echo "    commit: $(git log -1 --format='%h %s')"

echo "==> Budowanie i restart kontenerów"
# --wait czeka, aż healthchecki api i web przejdą; jeśli nie, deploy kończy się błędem
docker compose up -d --build --remove-orphans --wait --wait-timeout 300

echo "==> Sprzątanie starych obrazów (dysk ma tylko 30 GB)"
docker image prune -f

docker compose ps
echo "==> Gotowe"
