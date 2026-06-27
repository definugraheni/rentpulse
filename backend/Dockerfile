FROM mcr.microsoft.com/playwright/python:v1.54.0-jammy

WORKDIR /app

# Force Python to flush stdout/stderr immediately instead of buffering --
# without this, print() diagnostics may never show up in Railway's logs.
ENV PYTHONUNBUFFERED=1

COPY requirements.txt .

RUN pip install --no-cache-dir -r requirements.txt

RUN playwright install chromium

COPY . .

EXPOSE 8080

CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "8080"]