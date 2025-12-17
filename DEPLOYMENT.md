# GCP VM 部署指南

## 📋 前置需求

1. **GCP VM Instance**:
   - OS: Ubuntu 22.04 LTS
   - CPU: 2 vCPUs 以上
   - RAM: 8GB 以上
   - Disk: 30GB 以上

2. **已安裝軟體**:
   - Docker (20.10+)
   - Docker Compose (2.0+)
   - Git

3. **網路配置**:
   - 開放 Port 8000 (Backend API)
   - 開放 Port 8001 (Chainlit UI)
   - 設定防火牆規則允許外部訪問

## 🚀 部署步驟

### 1. 連接到 GCP VM

```bash
# SSH 連接
gcloud compute ssh your-instance-name --zone=your-zone

# 或使用傳統 SSH
ssh your-user@your-vm-external-ip
```

### 2. 安裝 Docker 和 Docker Compose (如未安裝)

```bash
# 更新系統
sudo apt-get update && sudo apt-get upgrade -y

# 安裝 Docker
curl -fsSL https://get.docker.com -o get-docker.sh
sudo sh get-docker.sh

# 將當前用戶加入 docker 組
sudo usermod -aG docker $USER

# 安裝 Docker Compose
sudo apt-get install docker-compose-plugin -y

# 登出並重新登入使群組生效
exit
```

### 3. Clone 專案

```bash
cd ~
git clone <your-repo-url> text2sql
cd text2sql
```

### 4. 設定環境變數

```bash
# 複製環境變數範例
cp .env.example .env

# 編輯環境變數
nano .env
```

**重要環境變數**:
```bash
# LLM API Key (必填)
GEMINI_API_KEY=your_actual_api_key

# MySQL 連接資訊
DB_HOST=your_mysql_host
DB_USER=your_mysql_user
DB_PASSWORD=your_mysql_password

# SSH Tunnel (如果 MySQL 需要 SSH)
SSH_HOST=your_ssh_host
SSH_USER=your_ssh_user
SSH_PASSWORD=your_ssh_password

# ClickHouse
CH_DB_HOST=your_clickhouse_host
CH_DB_PASSWORD=your_ch_password
```

### 5. 設定 SSH Keys (如使用 SSH Tunnel)

```bash
# 創建 ssh_keys 目錄
mkdir -p ssh_keys

# 複製 SSH private key
cp ~/.ssh/id_rsa ssh_keys/
chmod 400 ssh_keys/id_rsa

# 或生成新的 SSH key
ssh-keygen -t rsa -b 4096 -f ssh_keys/id_rsa -N ""
```

### 6. 構建和啟動容器

```bash
# 構建 Docker 映像
docker compose build

# 啟動服務 (背景執行)
docker compose up -d

# 查看日誌
docker compose logs -f

# 查看服務狀態
docker compose ps
```

### 7. 驗證部署

```bash
# 檢查 Backend API 健康狀態
curl http://localhost:8000/agent/playground

# 檢查 Chainlit UI (從瀏覽器訪問)
# http://your-vm-external-ip:8001
```

## 🔧 常用命令

### 服務管理

```bash
# 啟動服務
docker compose up -d

# 停止服務
docker compose stop

# 重啟服務
docker compose restart

# 停止並刪除容器
docker compose down

# 停止並刪除容器和 volumes
docker compose down -v
```

### 日誌查看

```bash
# 查看所有服務日誌
docker compose logs -f

# 查看特定服務日誌
docker compose logs -f backend
docker compose logs -f frontend

# 查看最近 100 行日誌
docker compose logs --tail=100 backend
```

### 更新部署

```bash
# 拉取最新代碼
git pull origin main

# 重新構建並啟動
docker compose down
docker compose build
docker compose up -d
```

## 🛡️ 安全性建議

### 1. 使用 HTTPS (推薦使用 Nginx Reverse Proxy)

創建 `nginx.conf`:

```nginx
server {
    listen 80;
    server_name your-domain.com;

    location / {
        proxy_pass http://localhost:8001;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }

    location /agent {
        proxy_pass http://localhost:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
    }
}
```

安裝 Certbot 並設定 SSL:

```bash
sudo apt-get install certbot python3-certbot-nginx -y
sudo certbot --nginx -d your-domain.com
```

### 2. 防火牆設定

```bash
# 只允許特定 IP 訪問
sudo ufw allow from your-office-ip to any port 8001
sudo ufw allow from your-office-ip to any port 8000

# 或允許所有 (不推薦用於生產環境)
sudo ufw allow 8000
sudo ufw allow 8001
```

### 3. 環境變數加密

使用 Google Secret Manager:

```bash
# 安裝 gcloud CLI
curl https://sdk.cloud.google.com | bash

# 登入
gcloud auth login

# 創建 secret
echo -n "your_api_key" | gcloud secrets create gemini-api-key --data-file=-

# 在 VM 上使用
export GEMINI_API_KEY=$(gcloud secrets versions access latest --secret="gemini-api-key")
```

## 📊 監控和維護

### 1. 資源監控

```bash
# 查看容器資源使用
docker stats

# 查看磁碟使用
df -h

# 清理未使用的 Docker 資源
docker system prune -a --volumes
```

### 2. 日誌輪替

編輯 `/etc/docker/daemon.json`:

```json
{
  "log-driver": "json-file",
  "log-opts": {
    "max-size": "10m",
    "max-file": "3"
  }
}
```

重啟 Docker:

```bash
sudo systemctl restart docker
docker compose restart
```

### 3. 自動重啟 (Systemd)

創建 `/etc/systemd/system/text2sql.service`:

```ini
[Unit]
Description=Text-to-SQL Agent
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
RemainAfterExit=yes
WorkingDirectory=/home/your-user/text2sql
ExecStart=/usr/bin/docker compose up -d
ExecStop=/usr/bin/docker compose down
TimeoutStartSec=0

[Install]
WantedBy=multi-user.target
```

啟用自動啟動:

```bash
sudo systemctl enable text2sql
sudo systemctl start text2sql
```

## 🐛 故障排除

### 問題 1: Backend 無法啟動

```bash
# 檢查日誌
docker compose logs backend

# 常見原因：
# 1. 環境變數未設定
# 2. 資料庫連接失敗
# 3. SSH Tunnel 無法建立
```

### 問題 2: Frontend 無法連接 Backend

```bash
# 檢查網路連接
docker compose exec frontend ping backend

# 檢查環境變數
docker compose exec frontend env | grep LANGSERVE_URL
```

### 問題 3: SSH Tunnel 連接失敗

```bash
# 測試 SSH 連接
docker compose exec backend ssh -i /root/.ssh/id_rsa user@ssh-host

# 檢查 SSH Key 權限
docker compose exec backend ls -la /root/.ssh/
```

### 問題 4: 記憶體不足

```bash
# 增加 swap
sudo fallocate -l 4G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile

# 永久啟用
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

## 📝 維護檢查清單

### 每週

- [ ] 檢查服務狀態: `docker compose ps`
- [ ] 查看錯誤日誌: `docker compose logs --tail=100 | grep ERROR`
- [ ] 檢查磁碟空間: `df -h`

### 每月

- [ ] 更新系統套件: `sudo apt-get update && sudo apt-get upgrade`
- [ ] 清理 Docker 資源: `docker system prune -a`
- [ ] 備份 `.env` 和資料庫
- [ ] 檢查並更新 dependencies: `uv lock --upgrade`

### 每季

- [ ] 更新 Docker 和 Docker Compose
- [ ] 檢查安全性補丁
- [ ] 審查日誌輪替策略
- [ ] 效能調優評估

## 🔗 有用連結

- [LangServe 文件](https://python.langchain.com/docs/langserve)
- [Chainlit 文件](https://docs.chainlit.io/)
- [Docker Compose 文件](https://docs.docker.com/compose/)
- [GCP VM 文件](https://cloud.google.com/compute/docs)

## 📞 支援

如有問題，請聯繫系統管理員或查看專案 Issue Tracker。
