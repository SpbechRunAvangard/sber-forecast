FROM python:3.11-slim

# Системные зависимости (libgomp1 нужен LightGBM)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential libgomp1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
ENV PYTHONPATH=/app \
    PYTHONUNBUFFERED=1

# Python-зависимости
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Приложение, код признаков и модель
COPY app/ ./app/
COPY src/ ./src/
COPY model/ ./model/

# Модель загружается в память при старте контейнера
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
