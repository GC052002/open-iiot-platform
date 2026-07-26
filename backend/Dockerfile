# Imagen del backend (F1). Multi-propósito: sirve tanto para el backend como para
# el simulador Modbus (ver docker-compose.yml).
FROM python:3.11-slim

WORKDIR /srv
ENV PYTHONUNBUFFERED=1 PYTHONPATH=/srv/backend

COPY pyproject.toml ./
COPY backend/ ./backend/

RUN pip install --no-cache-dir ".[dev]"

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
