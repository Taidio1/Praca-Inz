# Jeden obraz dla trzech procesów backendu (api, engine, marketdata): warstwy są
# współdzielone, więc na dysku serwera ląduje tylko raz.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# torch tylko w wersji CPU: domyślne koło z PyPI ciągnie CUDA (kilka GB)
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch

# Zależności z pyproject.toml osobno od kodu, żeby zmiana w src nie przebudowywała tej warstwy
COPY pyproject.toml ./
RUN python -c "import tomllib; print('\n'.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))" > requirements.txt \
    && pip install -r requirements.txt

COPY src ./src

RUN useradd --create-home --uid 10001 opes \
    && mkdir -p /home/opes/.cache/huggingface \
    && chown -R opes:opes /home/opes/.cache
USER opes

# Model embeddingów pobiera się raz do wolumenu (patrz docker-compose.yml)
ENV HF_HOME=/home/opes/.cache/huggingface

EXPOSE 8000
CMD ["uvicorn", "src.dashboard.api:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=*"]
