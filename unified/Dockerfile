FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml .
RUN pip install -e .

COPY . .

# Run combined app: REST API + MCP Streamable HTTP
CMD ["uvicorn", "src.combined:app", "--host", "0.0.0.0", "--port", "80"]
