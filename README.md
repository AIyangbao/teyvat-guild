# 提瓦特冒险家协会 · 委托服务平台

业务骨架对标黑马「苍穹外卖」，把外卖配送换成原神世界观的委托服务：玩家下单 → 支付 → 冒险家抢单 → 交付 → 验收 → 超时自动结算 → 评价。

**用 Python 重写而非照抄 Java**，重点不在功能覆盖，而在订单状态机、抢单并发与事务边界的正确性。项目已可用 Docker Compose 一键部署，前后端均已接线。

> 文档对齐原则：源码 > 本文档 > `docs/` 专题。若发现描述与代码不一致，以代码为准并顺手更新这里。

---

## 技术栈

| 层 | 选型 |
|---|---|
| 后端 | FastAPI 0.150、SQLAlchemy 2.1 异步（aiomysql）、Pydantic v2、Alembic 1.20、PyJWT |
| 前端 | Vue 3 + Vite 8 + Element Plus 2.14 + vue-router 5 + axios |
| 基础设施 | MySQL 8、Redis 7、Nginx（静态托管 + `/api` 反代）、Docker Compose |
| 测试 / 压测 | pytest（asyncio auto）、httpx ASGITransport、裸 socket 压测脚本 |

---

## 功能现状

### 后端

| 模块 | 主要入口 | 说明 |
|---|---|---|
| 认证与角色 | `POST /auth/register`、`/auth/login` | 注册时选 `player` / `adventurer`；选冒险家需填 `game_uid` / `server` / `game_nickname` 并同事务建 `Adventurer` 档案。`Literal` 白名单禁止公开注册自造 `admin` |
| 鉴权 | `app/core/deps.py` | 401 = 没登录/凭证失效，403 = 登录了但角色不对。`get_current_user` 每次查库，token 有效但账号被封照样拒 |
| 商品目录 | `/admin/categories`、`/admin/items` | 2 个 GET 公开（前台要看商品），5 个写接口统一挂 `require_admin`；`test_admin_auth.py` 用结构断言守住这个约定 |
| 委托生命周期 | `POST /commissions/create_order`、`/{id}/pay`、`/accept`、`/deliver`、`/confirm` | 下单价格快照 + 明细回填；抢单单语句 CAS；交付/确认走状态机 |
| 支付 | `POST /payments/{no}/callback` | 幂等回调：验签、金额校验、重复回调不二次推进状态 |
| 查询 | `GET /commissions/hall`、`/mine`、`/accepted`、`/{id}` | 大厅公开分页；`/accepted` 是冒险家侧「我接的委托」，必须注册在 `/{order_id}` 之前 |
| 评价 | `POST /commissions/{id}/review` | `commission_id` 唯一约束防重复评价；插入后全量 AVG 更新冒险家评分 |
| 超时与结算 | `app/tasks/timeout_scanner.py` | 三类候选：支付超时关单、接单超时自转移（3 次后关闭）、已完成满 7 天自动结算并累加 `finished_count` |
| 缓存 | `app/core/cache.py`、`app/services/cache_keys.py` | Redis 旁路缓存：精确失效 + TTL 30s + 故障降级；redis-py 8 已关默认重试（快失败） |
| 迁移 | `alembic/versions/`（4 个版本） | 容器启动自动 `alembic upgrade head`，新环境零手工建表 |

### 前端

`frontend/src/router/index.js` 共 5 页：`LoginView`（登录/注册，含身份选择与冒险家三件套）、`HallView`（大厅，按角色显隐「发起委托」/「接单」）、`OrdersView`（我的委托）、`AcceptedView`（冒险家「我的接单」+ 提交交付）、`OrderDetailView`（详情 + 支付 / 提交交付 / 确认验收 / 评价弹窗，按角色与状态显隐）。`/orders` 需 `role=player`、`/accepted` 需 `role=adventurer`，导航项按角色对称显隐；`/orders/:id` 只要求登录（详情接口公开，冒险家也要看自己接的单）。以上前端拦截均只做体验层，真正校验在 `get_current_player` / `get_current_adventurer`。

前端已接通完整主链路：下单 → 支付 → 冒险家接单 → 提交交付 → 待验收 → 玩家确认 → 评价 → 7 天自动结算。状态筛选项与后端 `ALL_STATES`（9 态）逐字对齐，写错会被 `list_mine` / `list_by_adventurer` 的 `STATE_INVALID` 拒绝。

**仍未做**：管理端界面（管理操作走 OpenAPI / curl）、UI 自动化测试。

---

## 快速开始（本地开发）

前置：Docker Desktop、Python venv、Node.js。以下命令默认已激活 venv（激活后直接用 `python` / `pip`，跨平台无路径歧义）。

```bash
# 1. 起 dev 依赖（MySQL 宿主端口 3308 + Redis）
docker compose -f docker-compose.dev.yml up -d

# 2. 配置：复制模板后把 DB_PORT 改成 dev 库的宿主端口
cp .env.example .env          # PowerShell: Copy-Item .env.example .env

# 3. 装依赖
pip install -r requirements.txt
cd frontend && npm ci && cd ..

# 4. 建表（dev 库首次/重建时）
alembic upgrade head

# 5. 起后端（注意用 python -m，别直接敲 uvicorn）
python -m uvicorn app.main:app --reload --port 8000
# → http://127.0.0.1:8000/docs

# 6. 另开终端起前端
cd frontend && npm run dev
# → http://127.0.0.1:5173

# 7. 跑测试
pytest -q
```

三个容易踩的点：

- **`python -m uvicorn`**：直接敲 `uvicorn` 时 `sys.path` 不含项目根，会报 `No module named 'app'`，必须用 `-m` 带上 cwd。测试那条已由 `pytest.ini` 的 `pythonpath = .` 修好，现在 `pytest -q` 与 `python -m pytest -q` 都能跑。
- **vite proxy 指向 `127.0.0.1:8000`**（`frontend/vite.config.js`），所以联调必须跑本机源码，别用容器里的旧镜像。
- `.env` 里 `DB_PORT` 本地是 3308，生产容器内部固定 3306（`docker-compose.yml` 会覆盖），两者别混。

---

## 测试与压测

- 全量：`pytest -q`。截至 2026-11-21 为 **209 passed / ~5s**（204 + 注册链路 5 例）。
- 用例分布：`app/tests/` 下 9 个测试文件 + `conftest.py`，覆盖状态机、安全、超时扫描、商品、委托流程、评价、结算、管理端鉴权、注册选角色。
- 约定：测试走真实 dev 库但**不留痕** —— `db` fixture 末尾 rollback；测路由时 override `get_db` 复用同一 session 且**故意不 commit**（真 `get_db` 会 commit，一提交 rollback 就撤不掉了）。
- 冒烟（起服务后可直接跑）：`scripts/smoke_jwt.py`、`scripts/smoke_payment.py`、`scripts/smoke_hall_cache.py`。
- 压测：`app/bench_accept_full.py`（真 JWT + 支付回调 + S1~S4）、`app/bench_hall_raw.py`（裸 socket 客户端，避开 httpx 客户端 CPU 饱和）。结论与三层判据见 [docs/bench_three_rulers.md](docs/bench_three_rulers.md)：单 worker 大厅约 1355 QPS / p50 6.6ms；缓存单发冷 16ms / 热 3.5ms。**Windows 下 `--workers` 多进程数字不可信**（accept 竞态丢连接），未在 Linux 复测前不要写进简历。

---

## 部署

```bash
docker compose up -d --build
```

生产栈三个服务：`mysql`（仅 compose 内网）、`redis`（仅内网）、`backend`（`expose: 8000`，不占宿主端口）、`frontend`（Nginx 托管静态并反代 `/api`）。宿主端口由 `.env` 的 `HTTP_PORT` 控制，默认 80；与同机其他项目共存时可改成别的。

- 容器启动流程在 `docker-entrypoint.sh`：等库就绪 → `alembic upgrade head` → uvicorn。
- 健康检查：`GET /` 返回 `{"status":"ok","service":"teyvat-guild"}`。
- 管理员账号由 `scripts/promote_admin.py` 提升（公开注册接口不接受 `role="admin"`）。
- 改了后端源码后需 `docker compose up -d --build backend` 重建镜像，否则容器里还是旧代码。

---

## 核心设计

- **订单状态机**：9 状态 / 16 事件 / 17 条合法转移，144 种组合全覆盖测试。转移表是纯数据，改表会被护栏测试拦下（`test_state_machine.py` 盯三个数字）。
- **抢单并发**：单语句 CAS —— `UPDATE ... WHERE status='待接单'`，`rowcount == 0` 即 `ACCEPT_CONFLICT`。由 InnoDB 当前读 + 行锁保证「判断与修改」不可分割，不用应用层锁。
- **一致性读**：RR 隔离级别下普通 `SELECT` 读事务快照，授权检查若用它，会读到抢单前的旧值（实测 1/20 概率返回 403）。归属校验一律 `with_for_update()`。更深的根因是 FastAPI 默认 `scope="request"` 让 commit 晚于响应，现已统一为 `DB = Depends(get_db, scope="function")`，commit 先于响应发送。
- **价格快照**：明细存下单时的单价与名称，服务项改价不影响历史订单。
- **超时扫描三条原则**：自转移必须推进 deadline、判定必须在锁内重查、一单一个事务。详见 [docs/timeout_scanner.md](docs/timeout_scanner.md)。
- **缓存失效收口**：写操作统一走精确失效，配合 TTL 30s 兜底；Redis 不可达时降级直查库，不让缓存拖垮主流程。
- **角色与权限**：注册端 `Literal` 白名单 + 管理端 `require_admin` 两道闸门；`get_current_adventurer` 同时校验 `role` 和 `Adventurer` 档案是否存在。
- **分层**：路由层只做编排与错误码映射，业务/状态转换下沉到 `services/`，保持不依赖 Request、可单测。

---

## 文档索引

| 文件 | 内容 |
|---|---|
| [DESIGN.md](DESIGN.md) | 业务定位、与苍穹外卖的模块映射（**设计稿，含未实现项**） |
| [SCHEMA.md](SCHEMA.md) | 表结构 DDL、设计决策、订单状态机 |
| [docs/bench_accept.md](docs/bench_accept.md) | 抢单并发压测报告（三层判据） |
| [docs/bench_three_rulers.md](docs/bench_three_rulers.md) | 压测方法论：QPS/TPS/RT、冷热同条件、客户端不是被测系统 |
| [docs/timeout_scanner.md](docs/timeout_scanner.md) | 超时扫描器：设计原则与验收证据 |
| [frontend/README.md](frontend/README.md) | 前端脚手架说明 |

---

## 已知局限

- 超时扫描挂在 `lifespan` 上，**web 进程不跑就不扫**；生产需独立调度进程或外部 cron。多 worker 时每个进程各跑一份，靠行锁 + 锁内重查做到「重复无害」，但不是「只跑一次」。
- 结算只由系统触发（`settle_order`），未暴露公网路由 —— 资金操作不应由客户端发起。
- 支付回调与超时关单竞态时事务回滚，payment 永远 pending；真实场景需退款/人工流程。
- Redis 未启用密码，靠「仅 compose 内网可达」保证边界；若日后暴露端口必须补认证。
- 评价状态未写进订单详情响应，老订单首屏仍显示「去评价」，点下去吃 409 才收起。
- 无管理端 UI、无 WebSocket 提醒、无统计报表。
