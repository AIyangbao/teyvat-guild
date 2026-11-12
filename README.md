# 提瓦特冒险家协会 · 委托服务平台

业务骨架对标黑马「苍穹外卖」，把外卖配送换成原神世界观的委托服务（玩家下单 → 冒险家抢单 → 交付 → 验收结算）。

技术栈：FastAPI + SQLAlchemy 2.x 异步 + MySQL 8 + Pydantic v2。**用 Python 重写而非照抄 Java**，重点不在功能覆盖，而在订单状态机与抢单并发的正确性。

---

## 已实现（后端）

| 能力 | 入口 | 验证方式 |
|---|---|---|
| 下单（价格快照 + 明细回填） | `POST /commissions/create_order` | 单测 + 冒烟：118.00 = 68×1 + 25×2 |
| **JWT 鉴权** | `POST /auth/register` `/login`；`core/security.py` + `core/deps.py` | 冒烟 12 条：401/403 分界、防枚举、封号查库、角色实时变更 |
| **支付（幂等回调）** | `POST /commissions/{id}/pay` → `POST /payments/{no}/callback` | 冒烟 9 条：发起幂等 / 验签 / 金额校验 / 重复回调不二次推进 |
| 抢单（CAS） | `POST /commissions/{id}/accept` | 压测 20 / 100 并发，结果恒为 `{200: 1, 409: N-1}` |
| 交付 / 确认 / 结算 | `POST .../deliver` `/confirm`；`settle()` | 归属校验 + 状态机单测 |
| 委托大厅 | `GET /commissions/hall` | 待接单分页，二次 `IN` 查询拼明细（固定 2 条 SQL） |
| 我的委托 | `GET /commissions/mine` | 按玩家过滤 + 可选状态筛选 |
| 订单详情 | `GET /commissions/{id}` | 明细 + 状态流转时间线 |
| 超时扫描 | `app/tasks/timeout_scanner.py` | 支付超时 28 单归零；接单超时自转移 3 次后关闭 |
| 管理端 CRUD | `/admin/categories` `/admin/items` | 单测 9 条 + 引用检查防误删分类 |

测试：**188 passed**（服务层直调 + security 纯函数）。
冒烟：`scripts/smoke_jwt.py`（12 条）+ `scripts/smoke_payment.py`（9 条），起服务后可直接跑。
已知架构修复：所有路由依赖改为 `DB = Depends(get_db, scope="function")`，**commit 先于响应发送**（否则客户端零延迟跟请求会读到未提交数据）。

## 未实现（明确边界，不是遗忘）

| 缺口 | 现状 | 影响 |
|---|---|---|
| 缓存 | 未引入 Redis | 大厅每次查库 |
| 前端 | 玩家端 4 页可演示（Vue3 + Element Plus）；无管理端界面、无 UI 自动化测试 | 管理操作仍走 OpenAPI |
| 统计 / WebSocket 提醒 / 评价售后 | 无 | — |
| 支付掉单处理 | 回调与超时关单竞态时事务回滚，payment 永远 pending | 真实场景需退款/人工流程 |
| 外键约束 / alembic 迁移 | 应用层引用检查 | 历史脏数据可绕过 |

## 核心设计

- **订单状态机**：9 状态 / 16 事件 / 17 条合法转移，144 种组合全覆盖测试。转移表是纯数据，改表会被护栏测试拦下（`test_state_machine.py` 盯三个数字）。
- **抢单并发**：单语句 CAS——`UPDATE ... WHERE status='待接单'`，`rowcount == 0` 即 `ACCEPT_CONFLICT`。不用应用层锁，由 InnoDB 当前读 + 行锁保证「判断与修改」不可分割。
- **一致性读的坑**：RR 隔离级别下普通 `SELECT` 读事务快照，授权检查若用它，会读到抢单前的旧值（实测 1/20 概率返回 403）。归属校验一律 `with_for_update()`。更深的根因是 FastAPI 默认 `scope="request"` 让 commit 晚于响应。
- **价格快照**：明细存下单时的单价与名称，服务项改价不影响历史订单。
- **超时扫描三条原则**：自转移必须推进 deadline、判定必须在锁内重查、一单一个事务。详见 [docs/timeout_scanner.md](docs/timeout_scanner.md)。

## 文档

| 文件 | 内容 |
|---|---|
| [DESIGN.md](DESIGN.md) | 业务定位、与苍穹外卖的模块映射、三条增量（**设计稿，含未实现项**） |
| [SCHEMA.md](SCHEMA.md) | 表结构 DDL、设计决策、订单状态机 |
| [docs/bench_accept.md](docs/bench_accept.md) | 抢单并发压测报告（三层判据） |
| [docs/timeout_scanner.md](docs/timeout_scanner.md) | 超时扫描器：设计原则与验收证据 |

## 快速开始

```bash
# 1. 起 MySQL（见 docker-compose.dev.yml，宿主机 3308）
docker compose -f docker-compose.dev.yml up -d

# 2. 装依赖（venv 已存在时跳过）
python -m venv venv && ./venv/Scripts/pip install -r requirements.txt

# 3. 跑测试
./venv/Scripts/python -m pytest -q

# 4. 起服务，看接口文档
./venv/Scripts/python -m uvicorn app.main:app --port 8000
# → http://127.0.0.1:8000/docs
```

## 已知局限

- 超时扫描挂在 `lifespan` 上，**web 进程不跑就不扫**；生产需独立调度进程或外部 cron。
- 多 worker 部署时每个进程各跑一份扫描器：靠行锁 + 锁内重查做到「重复无害」，但不是「只跑一次」。
- `settle()` 未暴露公网路由（资金操作应只由系统触发）。
