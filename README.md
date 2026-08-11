# SubManager

[![Test and publish Docker image](https://github.com/zj2xr7/SubManager/actions/workflows/docker.yml/badge.svg?branch=main)](https://github.com/zj2xr7/SubManager/actions/workflows/docker.yml)
[![GHCR](https://img.shields.io/badge/GHCR-ghcr.io%2Fzj2xr7%2Fsubmanager-blue?logo=docker)](https://github.com/zj2xr7/SubManager/pkgs/container/submanager)

SubManager 是一个本地优先的单用户订阅管理工具，统一核算支付宝与 USDT 银行卡两条支付链路的人民币成本，并提供 C2C 充值、余额管理和 Server 酱到期提醒。

## 功能

- 订阅增删改查，支持 USD、GBP、CAD、CNY 与月付、年付、自定义周期
- 支付宝链路：原价 × 实时 CNY 汇率
- 银行卡链路：原价 × USD 汇率 × 1.03 × C2C 单价
- 人民币 C2C 充值自动换算 USDT 并扣除 0.01 上链费
- 充值批次按 FIFO 消耗，订阅扣款保留逐批人民币成本组成与完整资金流水
- 可勾选银行卡订阅，按余额缺口计算建议充值人民币金额
- Dashboard 月均/年度支出、7 天内续费与余额预警
- ExchangeRate-API 汇率缓存、设置页实时报价与无 Key 时的参考汇率回退
- Server 酱每日到期提醒与当日去重
- 本地开发和 Docker 单容器部署

## 本地开发

### 后端

```powershell
cd backend
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uvicorn app.main:app --reload --port 8000
```

API 文档位于 <http://127.0.0.1:8000/docs>。

### 前端

```powershell
cd frontend
corepack enable
pnpm install --frozen-lockfile
pnpm run dev
```

打开 <http://127.0.0.1:5173>，Vite 会把 `/api` 转发到后端。

## 配置

复制 `.env.example` 为 `.env`，或在“设置”页面写入配置：

- `SERVER_CHAN_KEY`：Server 酱 SendKey
- `EXCHANGE_RATE_API_KEY`：ExchangeRate-API Key
- `DATABASE_URL`：SQLAlchemy SQLite 地址

无汇率 API Key 时应用仍可运行，但会使用内置参考汇率。设置 API Key 后汇率会缓存一小时。

## Docker

### 使用预构建镜像

```powershell
docker pull ghcr.io/zj2xr7/submanager:latest
docker run -d --name submanager --restart unless-stopped `
  -p 8000:8000 `
  -v submanager-data:/app/backend/data `
  ghcr.io/zj2xr7/submanager:latest
```

访问 <http://127.0.0.1:8000>。容器内 SQLite 数据保存在 `/app/backend/data`，请始终挂载数据卷。

### Docker Compose

```powershell
Copy-Item .env.example .env
docker compose pull
docker compose up -d
```

Compose 默认使用 `ghcr.io/zj2xr7/submanager:latest`，SQLite 数据持久化在根目录 `data/` 中。本地修改后可运行 `docker compose up -d --build` 覆盖构建。

镜像标签：

- `latest`、`main`：`main` 稳定分支
- `develop`：开发分支
- `1.0.0`、`1.0`、`1`：版本发布
- `sha-<commit>`：精确提交

## 测试与构建

```powershell
cd backend
python -m unittest discover -s tests -v

cd ..\frontend
pnpm run build
```

GitHub Actions 会在 Pull Request 中执行测试与 Docker 健康检查；推送 `main`、`develop` 或 `v*` 标签时，还会把 `linux/amd64` 镜像发布到 GHCR。

## Git 分支约定

- `main`：稳定发布
- `develop`：日常开发主线
- `feature/*`：从 `develop` 创建并合并回 `develop`
- `hotfix/*`：从 `main` 创建并合并回 `main` 与 `develop`

## License

[MIT](LICENSE) © 2026 zj2xr7
