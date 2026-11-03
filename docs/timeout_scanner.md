# 超时扫描器设计与验收

> 目标：把 `pay_deadline` / `accept_deadline` / `pool_retry` 三个字段接进真实流程，让「支付超时关单」和「接单超时回池」自动发生。
> 代码：`app/services/commission_timeout.py`（判定）+ `app/tasks/timeout_scanner.py`（调度壳）+ `app/main.py`（lifespan 挂载）。

---

## 1. 分工：判定在 services，调度在 tasks

最初的版本把判定和调度写在一起，并且硬编码 `AsyncSessionLocal`，导致这段逻辑**永远无法测试**——测试 fixture 的 `db` 处于未提交事务里，扫描器另开的连接读不到那份数据，任何测试都会写成「假绿」。

改造后职责清晰：

| 层 | 职责 | 是否 commit |
|---|---|---|
| `services/commission_timeout.py` | 锁单、判定、调 `transition()` | **否**，事务边界归调用方 |
| `tasks/timeout_scanner.py` | 拉候选 id、每单开 session、统计 | 是，一单一个事务 |
| `main.py` lifespan | 按 `scan_interval_sec` 循环调用 `scan_once()` | — |

调用的路由（将来的「玩家手动关闭」）也能复用同一套判定，不必重写。

## 2. 四条设计原则

### ① 自转移必须推进 `accept_deadline`

`(待接单, 超时无人接)` 是**自转移**：状态不变，只 `pool_retry += 1`。如果不推 deadline，下一轮扫描（60 秒后）立刻又命中同一单，`pool_retry` 一轮涨一，日志表会被同一张单刷爆。

代码里自转移后紧跟：

```python
order.accept_deadline = now_plus(minutes=settings.order_accept_timeout_min)
```

### ② 判定必须在 `with_for_update()` 锁内重查

这是自转移独有的坑：扫出来的 id 只是**候选**。两个 worker 同时扫到同一张单，第一个处理完提交后，第二个进来时状态**仍然**是「待接单」——不像「支付成功」那条边会抛 `STATE_ILLEGAL`，状态机完全拦不住，它会重复 +1。

唯一可靠的拦截点是拿到行锁后重新判断 `accept_deadline < utcnow()`。因为①已把 deadline 推到未来，第二个 worker 重查时条件不成立，自然跳过。

### ③ 一单一个事务

一批共用一个 session 时，第 N 单抛 `BizError` 会让整个事务 rollback，前 N-1 单的日志全部作废；而且整个过程长时间持有多行锁。

所以 `scan_once` 里「拉候选」和「处理」是两个分离的阶段：拉候选的 `async with` 只读 id，读完立刻退出。

### ④ 到顶必须有终止路径

无限自转移没有终点。`pool_retry >= max_pool_retry` 时改走 `(待接单, 无人接单关闭, 已取消)`，与玩家的「取消」区分开，日志里一眼能看出是系统关的。

状态机为此补了一条边：

```python
(PENDING_ACCEPT, "无人接单关闭"): CANCELED,   # pool_retry 到顶的终止路径
```

加边后 `test_state_machine.py` 的三个护栏数字（事件数 15→16、合法边 16→17、全组合 135→144）全部报警——这正是护栏存在的意义。

## 3. 配置

```python
order_pay_timeout_min   = 30    # 支付截止
order_accept_timeout_min = 15   # 每轮接单窗口
max_pool_retry          = 3     # 自转移上限
scan_interval_sec       = 60    # 扫描周期
```

## 4. 验收证据

### 4.1 支付超时（首次上线）

库里有 28 张压测遗留的待支付单（`pay_deadline` 全部过期）：

```
python -m app.tasks.timeout_scanner
→ {'pay_timeout_closed': 28, 'accept_timeout_retried': 0}
```

| 检查项 | 结果 |
|---|---|
| 状态分布 | 待支付 **28 → 0**，已关闭 28 |
| 日志条数 | `支付超时 / system` **恰好 28 条**，一条不多 |
| 重复执行 | 再跑一轮 `0/0`，幂等 |

### 4.2 接单超时：完整生命周期（订单 217）

把 `accept_deadline` 手动改到过去，重复触发，观察 `pool_retry` 与时间线：

| 轮次 | `pool_retry` | `accept_deadline` | 状态 | 日志事件 |
|---|---|---|---|---|
| 初始 | 0 | 09:15 | 待接单 | `支付成功` |
| 1 | 1 | 09:15 → 11:15 | 待接单 | `超时无人接` |
| 2 | 2 | 11:07 → 11:23 | 待接单 | `超时无人接` |
| 3 | **3** | 13:01（继续推） | 待接单 | `超时无人接` |
| 4 | 3（不再涨） | **不动** | **已取消** | `无人接单关闭` |

关键观察：第 4 轮走终止边后 deadline 不再被更新——终止路径与自转移路径确实分开。真实时间对应 15 分钟 × 3 = 45 分钟后关单。

### 4.3 可观测性

扫描结果原本被静默丢弃：uvicorn 只给 `uvicorn.*` 装 handler，root logger 停在 WARNING，`logger.info` 直接没了。修法是在 `lifespan` 最前面 `logging.basicConfig(level=INFO, force=True)`（必须晚于 uvicorn 的 dictConfig 执行），现在能看到：

```
2026-11-03 20:46:19,945 INFO    app.main: timeout scan: {'pay_timeout_closed': 0, 'accept_timeout_retried': 1}
```

只在 `any(stats.values())` 时打印，避免空轮次刷屏。

## 5. 已知局限

1. **寄生在 web 进程**：扫描器挂在 `lifespan` 上，服务停了就不扫。实测 217 的 deadline 在 17:15（北京）过期，直到 19:00 服务启动才被处理，中间 1 小时 45 分钟无人管。生产应拆成独立调度进程或外部 cron 触发内部端点。
2. **多 worker 重复扫描**：`uvicorn --workers 4` 就是 4 份循环。靠行锁 + 锁内重查做到「重复无害」，但不是「只跑一次」。要单实例需 Redis 分布式锁或独立调度。
3. **非业务异常会终止整轮**：`_run_one` 只捕 `BizError`，`IntegrityError` 之类会冒出 `scan_once`，本轮剩余单子等下一轮处理（外层 `except Exception` 保证循环不死）。
4. **候选查询走索引但未分页游标**：单轮上限 `BATCH=100`，积压超过 100 单需要多轮消化，按 `deadline` 升序保证最老的先处理。

## 6. 复现步骤

```bash
# 全量测试（含 7 条超时判定用例）
./venv/Scripts/python -m pytest app/tests/test_timeout_scanner.py -q

# 手动跑一轮（库里有过期单时才有输出）
./venv/Scripts/python -m app.tasks.timeout_scanner

# 造接单超时素材：把某张待接单的 deadline 改到过去，重启服务观察日志
# UPDATE commission SET accept_deadline = UTC_TIMESTAMP() - INTERVAL 1 MINUTE WHERE id = ?;
```

脚本入口用 `_main()` 包一层 `await engine.dispose()`，否则 `asyncio.run()` 结束后连接池里的连接会在 loop 关闭后才被 GC 回收，stderr 刷 `Event loop is closed`。
