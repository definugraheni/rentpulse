FROM mcr.microsoft.com/playwright/python:v1.60.0-jammy

WORKDIR /app

ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install --with-deps chromium

COPY . .

CMD ["sh", "-c", "uvicorn api:app --host 0.0.0.0 --port $PORT"]