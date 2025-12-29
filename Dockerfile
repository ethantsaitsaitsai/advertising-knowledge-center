# ==========================================
# Stage 1: Builder (負責安裝依賴，產生虛擬環境)
# ==========================================
FROM python:3.12-slim-bookworm AS builder

# 安裝 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

WORKDIR /app

# 安裝系統依賴 (僅編譯期需要)
RUN apt-get update && apt-get install -y --no-install-recommends \
    git \
    && rm -rf /var/lib/apt/lists/*

# 1. 複製依賴定義
COPY pyproject.toml uv.lock ./

# 2. 安裝依賴 (產生 .venv)
# --frozen: 鎖定版本
# --no-dev: 不安裝開發依賴 (pytest 等)，節省空間
RUN uv sync --frozen --no-dev --no-install-project

# ==========================================
# Stage 2: Runner (最終極簡映像檔)
# ==========================================
FROM python:3.12-slim-bookworm AS runner

# 只安裝 Runtime 真正需要的系統工具
# openssh-client: 您的專案需要 SSH Tunnel 連資料庫，所以必須留著
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# 從 Builder 階段只複製虛擬環境
COPY --from=builder /app/.venv /app/.venv

# 複製專案程式碼
COPY . .

# 設定環境變數
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8000 8001

# 預設指令 (使用 exec 形式，讓 python 成為 PID 1，節省記憶體)
CMD ["python", "backend/server.py"]
