# Clean-room smoke test of the npm tarball. Build context: a folder holding only
# the packed tarball and smoke_mcp.mjs. Nothing from the host is mounted.
#   docker build -t ai-detect-smoke -f scripts/docker-smoke/Dockerfile <context>
#   docker run --rm ai-detect-smoke
FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends nodejs npm ca-certificates \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv
# CPU-only PyTorch: the default Linux wheel pulls several GB of CUDA libraries.
ENV UV_EXTRA_INDEX_URL=https://download.pytorch.org/whl/cpu \
    UV_INDEX_STRATEGY=unsafe-best-match \
    AI_DETECT_DEVICE=cpu HF_HUB_DISABLE_PROGRESS_BARS=1
WORKDIR /smoke
COPY houtini-ai-detect-*.tgz smoke_mcp.mjs ./
RUN echo '{"name":"smoke","private":true}' > package.json \
    && npm install --no-audit --no-fund --ignore-scripts ./houtini-ai-detect-*.tgz
CMD ["sh", "-c", "node --version && python --version && uv --version && node smoke_mcp.mjs node node_modules/@houtini/ai-detect/bin/ai-detect-mcp.js"]
