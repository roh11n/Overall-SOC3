FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONDONTWRITEBYTECODE=1

WORKDIR /app/backend

# Build tooling needed by a few wheels (pandas, python-pptx, jq bindings, etc.)
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --extra-index-url https://d33sy5i8bnduwe.cloudfront.net/simple/ -r requirements.txt

COPY . .

EXPOSE 8001

# All runtime config comes from environment (see docker-compose.yml / .env).
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8001"]
