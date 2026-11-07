FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

COPY requirements.lock /tmp/requirements.lock
RUN python -m pip install --no-cache-dir -r /tmp/requirements.lock

COPY pyproject.toml requirements.txt ./
COPY src ./src
RUN python -m pip install --no-cache-dir --no-deps .

COPY k8s ./k8s
RUN mkdir -p /home/tribal/.local/share/fastmcp \
    && chown -R 10001:10001 /home/tribal

ENV HOME=/home/tribal \
    FASTMCP_HOME=/home/tribal/.local/share/fastmcp \
    K8S_TEMPLATE_ROOT=/app/k8s

USER 10001:10001
EXPOSE 8000
