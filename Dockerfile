# Smart Reading Queue — single-process image (bot + scheduler + /health).
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    DB_PATH=/data/rq.db \
    HF_HOME=/data/hf-cache

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates sqlite3 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir uv

# Install deps first (cache layer). The editable package needs src + README.
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --frozen --no-dev

# Runtime assets (prompts are loaded at startup; migrations applied on boot).
COPY prompts ./prompts
COPY migrations ./migrations
COPY interests.yaml ./
COPY evals ./evals
COPY scripts ./scripts

EXPOSE 8080
VOLUME ["/data"]

# Runs long-polling + the weekly digest scheduler + the /health server.
CMD ["uv", "run", "rq", "bot"]
