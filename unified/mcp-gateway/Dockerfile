FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONPATH=/app/src

WORKDIR /app

# Build context is ./unified — copy gateway package first
COPY mcp-gateway/pyproject.toml .
RUN pip install -e ".[http]"

COPY mcp-gateway/src ./src
COPY src/common ./src/common

# Place contracts at the root of /app, so parents[2] from /app/src/xxx.py points to /app/contracts
COPY contracts ./contracts

CMD ["python", "-m", "src.mcp_http"]
