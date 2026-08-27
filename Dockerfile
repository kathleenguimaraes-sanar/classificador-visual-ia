
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# ffmpeg é usado via subprocess (src/portfolio/frames.py e
# transcription.py) e não é instalável via pip.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

# Instala o Chromium do Playwright junto com as dependências
# de sistema necessárias (--with-deps cobre libs como libnss3,
# libatk, libgtk etc., que não existem na imagem slim).
RUN python -m playwright install --with-deps chromium

COPY . .

# Fallback para execução local via `docker run` sem disco
# persistente montado. No Render, CETRUS_DATA_DIR deve apontar
# para o Persistent Disk (ver render.yaml).
RUN mkdir -p /app/data

EXPOSE 8000

# Forma shell (não exec) para permitir a expansão de $PORT,
# que o Render injeta em tempo de execução.
CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
