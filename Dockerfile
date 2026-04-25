FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CDSAPI_RC=/home/appuser/.cdsapirc

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt /app/requirements.txt

RUN python -m pip install --no-cache-dir --upgrade pip \
    && python -m pip install --no-cache-dir -r /app/requirements.txt

RUN useradd --create-home --uid 10001 appuser

COPY --chown=appuser:appuser api /app/api
COPY --chown=appuser:appuser frontend /app/frontend

RUN mkdir -p /app/data/raw/glofas /app/data/processed /app/tmp \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

CMD ["uvicorn", "api.app:app", "--host", "0.0.0.0", "--port", "8000"]
