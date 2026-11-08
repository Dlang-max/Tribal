# Package the built React dashboard, Codex CLI, runtime, and validation resources.
FROM node:22-bookworm-slim AS frontend
WORKDIR /gui
COPY src/knowledge-base-gui/package.json src/knowledge-base-gui/package-lock.json ./
RUN npm ci
COPY src/knowledge-base-gui ./
RUN npm run build

FROM node:22-bookworm-slim AS codex-cli
RUN npm install --global @openai/codex@0.167.0

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1
COPY --from=codex-cli /usr/local/bin/node /usr/local/bin/node
COPY --from=codex-cli /usr/local/lib/node_modules /usr/local/lib/node_modules
RUN ln -s /usr/local/lib/node_modules/@openai/codex/bin/codex.js /usr/local/bin/codex
WORKDIR /app
COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir -r /tmp/requirements.lock
COPY pyproject.toml requirements.txt ./
COPY src/tribal-mcp-server ./src/tribal-mcp-server
COPY agent-knowledge-base/specs ./agent-knowledge-base/specs
COPY agent-knowledge-base/validation ./agent-knowledge-base/validation
COPY --from=frontend /gui/dist ./gui
RUN python -m pip install --no-cache-dir --no-deps . \
    && mkdir -p /home/tribal/.codex \
    && chown -R 10001:10001 /home/tribal
ENV HOME=/home/tribal \
    CODEX_HOME=/home/tribal/.codex \
    HOST=0.0.0.0 \
    TRIBAL_SPEC_ROOT=/app/agent-knowledge-base/specs/v1 \
    TRIBAL_VALIDATOR_PATH=/app/agent-knowledge-base/validation/v1/validate_knowledge_base_notes.py \
    TRIBAL_GUI_DIRECTORY=/app/gui
USER 10001:10001
EXPOSE 8000
CMD ["tribal-mcp-server"]
