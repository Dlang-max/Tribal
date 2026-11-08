# Package and run Tribal's basic HTTP MCP server.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app
COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir -r /tmp/requirements.lock

COPY pyproject.toml requirements.txt ./
COPY src/tribal-mcp-server ./src/tribal-mcp-server
RUN python -m pip install --no-cache-dir --no-deps . \
    && mkdir -p /home/tribal \
    && chown 10001:10001 /home/tribal

ENV HOME=/home/tribal \
    HOST=0.0.0.0
USER 10001:10001
EXPOSE 8000
CMD ["tribal-mcp-server"]
