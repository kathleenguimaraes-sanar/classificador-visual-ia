
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app


RUN apt-get update \
    && apt-get install -y --no-install-recommends ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt


RUN python -m playwright install --with-deps chromium

COPY . .


RUN mkdir -p /app/data

EXPOSE 8000


CMD uvicorn app:app --host 0.0.0.0 --port ${PORT:-8000}
