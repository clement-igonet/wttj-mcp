FROM python:3.12-slim

WORKDIR /app

# Install build deps then clean up to keep image small
RUN pip install --no-cache-dir hatchling

COPY pyproject.toml .
COPY src/ src/

RUN pip install --no-cache-dir .

# MCP servers communicate over stdio — no port needed
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["wttj-mcp"]
