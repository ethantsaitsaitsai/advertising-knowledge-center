FROM python:3.11-slim-bookworm AS base

# 安裝系統依賴
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

# 安裝 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 設定工作目錄
WORKDIR /app

# 複製依賴檔案
COPY pyproject.toml uv.lock ./

# 安裝依賴 (使用 system python)
RUN uv sync --frozen --no-install-project

# 複製專案代碼
COPY . .

# 設定環境變數
ENV PYTHONPATH=/app
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8000 8001

# 健康檢查
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/agent/playground || exit 1

# 預設指令 (會被 docker-compose 覆蓋)
CMD ["uv", "run", "server.py"]
