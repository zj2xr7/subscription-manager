# Subscription Manager

[![Test and build Docker image](https://github.com/zj2xr7/subscription-manager/actions/workflows/docker.yml/badge.svg?branch=main)](https://github.com/zj2xr7/subscription-manager/actions/workflows/docker.yml)

Subscription Manager（SubManager）是一个本地优先的单用户订阅管理工具，用于统一核算支付宝与 USDT 银行卡支付链路的人民币成本，并提供 C2C 充值、余额管理和 Server 酱到期提醒。

## 功能

- 管理 USD、GBP、CAD、CNY 订阅及多种计费周期
- 支付宝订阅按实时汇率换算人民币成本
- USDT 充值批次按 FIFO 核算真实人民币成本
- 根据银行卡余额和续费队列估算充值缺口
- 展示月均支出、年度支出、近期续费、扣款记录和通知状态
- 使用 ExchangeRate-API 获取汇率，无 Key 时回退到参考汇率
- 支持 Server 酱多节点到期提醒、通知去重和发送历史
- 支持本地开发及 Docker Compose 部署

## 本地开发

### 后端

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

API 文档位于 <http://127.0.0.1:8000/docs>。

### 前端

```bash
cd frontend
corepack enable
pnpm install --frozen-lockfile
pnpm run dev
```

打开 <http://127.0.0.1:5173>，Vite 会将 `/api` 转发到后端。

## 配置

```bash
cp .env.example .env
```

也可以在应用的“设置”页面写入配置：

- `SERVER_CHAN_KEY`：Server 酱 SendKey
- `EXCHANGE_RATE_API_KEY`：ExchangeRate-API Key
- `DATABASE_URL`：SQLAlchemy SQLite 地址

未设置汇率 API Key 时应用仍可运行，并使用内置参考汇率。

## Docker

项目不使用预构建镜像，每次部署均从当前源码构建。

### 环境要求

- Git
- Docker Engine 24 或更高版本
- Docker Compose v2 插件
- 主机的 `8000` 端口可用

确认环境：

```bash
git --version
docker --version
docker compose version
```

### 首次部署

克隆仓库并进入项目目录：

```bash
git clone https://github.com/zj2xr7/subscription-manager.git
cd subscription-manager
```

创建本地配置文件：

```bash
cp .env.example .env
```

根据需要编辑 `.env` 中的 Server 酱和汇率 API Key，然后构建并启动服务：

```bash
docker compose up -d --build
```

检查容器和接口状态：

```bash
docker compose ps
curl --fail http://127.0.0.1:8000/api/health
```

浏览器访问 <http://127.0.0.1:8000>。

Compose 会在本地创建 `subscription-manager:local` 镜像，并将 SQLite 数据持久化到项目根目录的 `data/`。更新代码后再次运行：

### 更新部署

```bash
cd subscription-manager
git pull --ff-only origin main
docker compose up -d --build
```

### 日常运维

查看状态和实时日志：

```bash
docker compose ps
docker compose logs -f
```

停止服务：

```bash
docker compose down
```

重启服务：

```bash
docker compose restart
```

SQLite 数据保存在 `data/`，执行 `docker compose down` 不会删除这些数据。升级或迁移前可备份整个目录：

```bash
tar -czf subscription-manager-data-backup.tar.gz data/
```

## 测试与构建

```bash
cd backend
python -m unittest discover -s tests -v

cd ../frontend
pnpm install --frozen-lockfile
pnpm run build
```

GitHub Actions 会在推送、版本标签和 Pull Request 中执行后端测试、前端生产构建、Docker 源码构建及容器健康检查。CI 只验证镜像，不推送到镜像仓库。

## Git 分支约定

- `main`：稳定发布
- `develop`：日常开发主线
- `feature/*`：从 `develop` 创建并合并回 `develop`
- `hotfix/*`：从 `main` 创建并合并回 `main` 与 `develop`

## License

[MIT](LICENSE) © 2026 zj2xr7
