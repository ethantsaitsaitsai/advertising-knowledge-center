# Dockerfile
FROM python:3.12-slim-bookworm

# 安裝系統依賴
# openssh-client: 用於 SSH Tunnel
# curl: 用於健康檢查
# git: 有些 python套件可能需要 git
RUN apt-get update && apt-get install -y --no-install-recommends \
    openssh-client \
    curl \
    git \
    && rm -rf /var/lib/apt/lists/*

# 安裝 uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /bin/uv

# 設定工作目錄
WORKDIR /app

# 1. 先複製依賴定義檔 (利用 Docker Layer Cache)
COPY pyproject.toml uv.lock ./

# 2. 安裝依賴
# --frozen: 嚴格依照 lock 檔安裝
# --no-install-project: 暫不安裝專案本身 (只安裝 dependencies)
RUN uv sync --frozen --no-install-project

# 3. 複製其餘程式碼
COPY . .

# 4. 安裝專案本身 (如果有的話) 及更新環境變數
RUN uv sync --frozen

# 設定環境變數
# 讓 uv 使用虛擬環境
ENV PATH="/app/.venv/bin:$PATH"
ENV PYTHONPATH=/app
ENV PYTHONUNBUFFERED=1

# 暴露端口
EXPOSE 8000 8001

# 預設指令
CMD ["uv", "run", "server.py"]