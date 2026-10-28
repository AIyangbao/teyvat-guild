# 并发抢单压测报告（bench_accept）

> 目标：验证「同一委托被 N 个冒险家并发抢夺时，只有 1 个成功」这一不变量在真实数据库 + 真实 HTTP 下成立。
> 项目：teyvat-guild（FastAPI + MySQL 8.4 + SQLAlchemy 2.x 异步）
> 日期：2026-10-27（手工重置版） / 2026-10-28（全链路版）

---

## 1. 被测实现

抢单不使用应用层锁，而是**单语句 CAS**：把状态判断写进 `UPDATE` 的 `WHERE`，由 InnoDB 的行锁 + 当前读保证「判断与修改」不可分割。

```python
# app/services/commission_state.py
result = await db.execute(
    update(Commission)
    .where(Commission.id == order_id,
           Commission.status == PENDING_ACCEPT)   # 状态必须在 WHERE 里
    .values(status=IN_PROGRESS,
            adventurer_id=adventurer_id,
            accepted_at=utcnow())
)
if result.rowcount == 0:
    raise BizError("手慢了，该委托已被接走", code="ACCEPT_CONFLICT")
```

`rowcount == 0` 的语义不是「订单不存在」，而是「要改的那一行在当时不满足条件」——被别人抢了、还没支付、已取消，都归为「手慢了」，接口统一返回 409。

**为什么不用 `SELECT ... FOR UPDATE` + 改**：功能等价但会让 19 个请求排队等锁，逐个醒来后逐个失败。CAS 下失败者立即返回，无排队（详见第 7 节「两种并发策略的分工」）。

---

## 2. 环境

| 项 | 值 |
|---|---|
| 机器 | 笔记本 斗战者 N176B 2025 / i7-14650HX / 16G DDR5 |
| OS | Windows 11 |
| Python | 3.13.14（venv） |
| Web | FastAPI 0.150.0 + Uvicorn 0.54.0 |
| ORM | SQLAlchemy 2.1.5（async）+ aiomysql 0.3.2 |
| DB | MySQL 8.4（Docker 容器 `teyvat-mysql`，宿主端口 3308） |
| 客户端 | httpx 0.28.1（`trust_env=False`，绕开本机 HTTP_PROXY） |
| 服务形态 | 第 3、4 组：单 worker；第 5 组：`--workers 4`；第 6 组：单 worker |
| 连接池 | `pool_size=10, max_overflow=20`（每 worker 上限 30） |

---

## 3. 方法

### 3.1 三层判据（缺一不可）

| 层 | 看什么 | 为什么必须 |
|---|---|---|
| L1 协议层 | 状态码分布 = `{200: 1, 409: N-1}` | 应用是否按预期拒绝 |
| L2 数据层 | `commission.status='进行中'`、`adventurer_id` 唯一非空 | 是否只被改了一次 |
| L3 审计层 | 该单 `commission_log` 中 `event='抢单成功'` **恰好 1 条** | 抓「接口返回对但写了多条日志/被覆盖」这类静默错 |

只看 L1 会漏掉一类失败：返回 409 但日志多写了一条，或 `adventurer_id` 被后到的请求覆盖 —— 这类 bug 只有查库才看得见。

### 3.2 两个版本的脚本

**A. 手工重置版（`bench_accept_stdlib.py`，2026-10-27）**

每轮开始前手工把订单改回初始态：

```sql
UPDATE commission SET status='待接单', adventurer_id=NULL, accepted_at=NULL WHERE id=1;
DELETE FROM commission_log WHERE commission_id=1 AND event='抢单成功';
```

- 验证的是：**抢单这一步的原子性**
- 局限：起点是人工构造的（真实业务里订单不会自己倒回「待接单」），且每轮证据被删除，**不可复现**

**B. 全链路版（`app/bench_accept_full.py`，2026-10-28）**

每轮真实走前置链路，不删库、不重置：

```
POST /commissions/create_order   → 拿 order_id
POST /commissions/{id}/pay       → 待接单（真实状态机流转）
20 × POST /commissions/{id}/accept（并发）→ 1×200 + 19×409
```

- 验证的是：**下单 → 支付 → 可抢 → 互斥**整条链路
- 证据永久留在库里，按 `order_id` 分组即可复现、可审计

---

## 4. 结果

### 4.1 单进程（1 worker）

| 轮次 | 并发 | 状态码分布 | 赢家 | 抢单日志数 |
|---|---|---|---|---|
| 1 | 20 | `{200:1, 409:19}` | 100 | 1 |
| 2 | 20 | `{200:1, 409:19}` | 100 | 1 |
| 3 | 20 | `{200:1, 409:19}` | 105 | 1 |
| 4 | 100 | `{200:1, 409:99}` | 100 | 1 |

100 并发总耗时 **0.53s**（热态，见第 6 节局限）。

### 4.2 多进程（4 workers，独立连接池，共享同一 MySQL）

| 轮次 | 并发 | 状态码分布 | 赢家 | 抢单日志数 |
|---|---|---|---|---|
| 1 | 20 | `{200:1, 409:19}` | 103 | 1 |
| 2 | 20 | `{200:1, 409:19}` | 102 | 1 |
| 3 | 20 | `{200:1, 409:19}` | 104 | 1 |
| 4 | 100 | `{200:1, 409:99}` | 122 | 1 |

压测后 `information_schema.PROCESSLIST` 41 条连接（4 worker × 约 10，懒创建）。

### 4.3 全链路（单 worker，2026-10-28）

```
第1轮 order_id=17  {200: 1, 409: 19}
第2轮 order_id=18  {200: 1, 409: 19}
第3轮 order_id=19  {200: 1, 409: 19}
PASS: 3轮, 每轮1成功19冲突
```

库内验收：

```sql
SELECT commission_id, COUNT(*) FROM commission_log
WHERE event='抢单成功' AND commission_id IN (17,18,19)
GROUP BY commission_id;
-- (17, 1) (18, 1) (19, 1)
```

每单日志轨迹（完整两条、顺序正确）：

```
17: 待支付 → 待接单 (支付成功, operator=1)
17: 待接单 → 进行中 (抢单成功, operator=200)
```

三轮订单 `status='进行中'`、`adventurer_id=200`、`total_amount=68.00`，永久留库可复现。

### 4.4 事务健康度核查（2026-10-27）

| 指标 | 结果 |
|---|---|
| `information_schema.INNODB_TRX` | 0（无悬挂事务） |
| `INNODB_LOCK_WAITS` | 0（无锁等待残留） |
| 失败请求是否写入 | 否 —— `UPDATE` 匹配 0 行，数据库层零修改 |

失败的请求不是「写入后回滚」，而是**从没写入**；但事务仍必须回滚（`get_db` 依赖统一 `rollback`），否则连接归还池子时事务未结束，下一个请求会读到旧快照。

---

## 5. 结论

> 委托抢单用单语句 CAS（`UPDATE ... WHERE status='待接单'`）保证原子性，不依赖应用层锁。
> 实测 **4 worker 多进程 + 100 并发，仍然只有 1 个请求成功、99 个 409，数据库审计日志恰好 1 条**，连续多轮稳定；
> 全链路版本（真实下单 + 支付后并发抢）同样成立，证据留库可复现。

原因是保证来自存储引擎而非应用进程：InnoDB 对目标行加排他锁，后来的语句挂起等锁，第一个事务提交后它们**按最新提交版本重新求值 `WHERE`**（当前读），条件不再满足 → 匹配 0 行。因此换进程、换机器、换语言，结论不变。

---

## 6. 局限性（必须声明，不能藏）

1. **单机、同库**：4 worker 在同一台机器、同一个 MySQL 实例上。跨机器、跨可用区、主从延迟场景未覆盖。
2. **热态数据**：多组数据是在 MySQL buffer pool 与连接池已预热后采集的。冷启动（`docker restart teyvat-mysql` 后立刻压）数字会明显变差，引用性能数字时必须标注冷/热。
3. **赢家分布受发射顺序影响**：`asyncio.gather` 按列表顺序发起请求，单进程 + 单事件循环下第一个协程几乎总是最先到达。因此「每轮赢家是否不同」**不是并发正确性的判据**，判据只有 L1+L2+L3 三层。
4. **重置版的前提是人工构造的**：4.1 / 4.2 两组每轮起点由 `UPDATE` 手工摆出，绕过了状态机，只验证抢单这一步，不验证「支付后可抢」的前置链路 —— 该缺口由 4.3 全链路版补上。
5. **未覆盖**：重复提交（同一冒险家连点）、订单不存在、已取消订单的并发行为；未做长时间持续压测与内存/连接泄漏观察。
6. **鉴权是假的**：`X-Adventurer-Id` 直接取自请求头，任何人可冒充任何冒险家。压测不受影响，但这是上线前必须替换的安全缺口。

---

## 7. 附：两种并发策略的分工

| | `SELECT ... FOR UPDATE` + 改 | `UPDATE ... WHERE 条件`（CAS） |
|---|---|---|
| 适用 | 转移逻辑复杂（要读字段算分支、写多条日志） | 简单状态切换 |
| 并发 | 排队，N 个请求串行 | 不等待，失败立即返回 |
| 本项目 | `transition()` 走这条 | 抢单 `accept_order()` 走这条 |
| 代价 | 吞吐随并发线性下降 | 绕过统一入口，**日志需手补** |

两者不冲突，但不能在同一个操作里混用。CAS 放弃统一入口的代价就是：日志完整性要自己保证 —— 这也是为什么 L3 判据（日志恰好 1 条）是本报告的核心。

---

## 8. 复现步骤

前置：MySQL 容器已起（`docker start teyvat-mysql`）、服务已起（`uvicorn app.main:app`）、`service_item` 表有在架商品（`id=1, status=1`）。

```powershell
# 全链路版（推荐）
python app/bench_accept_full.py

# 校验（Navicat 或命令行）
SELECT commission_id, COUNT(*) AS cnt FROM commission_log
WHERE event='抢单成功' GROUP BY commission_id ORDER BY commission_id DESC LIMIT 5;
```

期望：脚本输出 3 轮均为 `{200: 1, 409: 19}`；SQL 每单 `cnt = 1`。

相关文件：
- `app/bench_accept_full.py` — 全链路压测脚本（本报告 4.3）
- `app/services/commission_state.py` — 被测 CAS 实现
- `app/tests/test_commission_flow.py` — 服务层回归测试（含 `ACCEPT_CONFLICT` 用例）
