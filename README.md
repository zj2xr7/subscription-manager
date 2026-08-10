# SubManager

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
npm install
npm run dev
```

打开 <http://127.0.0.1:5173>，Vite 会把 `/api` 转发到后端。

## 配置

复制 `.env.example` 为 `.env`，或在“设置”页面写入配置：

- `SERVER_CHAN_KEY`：Server 酱 SendKey
- `EXCHANGE_RATE_API_KEY`：ExchangeRate-API Key
- `DATABASE_URL`：SQLAlchemy SQLite 地址

无汇率 API Key 时应用仍可运行，但会使用内置参考汇率。设置 API Key 后汇率会缓存一小时。

## Docker

```powershell
Copy-Item .env.example .env
docker compose up --build
```

访问 <http://127.0.0.1:8000>。SQLite 数据持久化在根目录 `data/` 中。

## 测试与构建

```powershell
cd backend
python -m unittest discover -s tests -v

cd ..\frontend
npm run build
```

## Git 分支约定

- `main`：稳定发布
- `develop`：日常开发主线
- `feature/*`：从 `develop` 创建并合并回 `develop`
- `hotfix/*`：从 `main` 创建并合并回 `main` 与 `develop`
