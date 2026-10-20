# 数据模型与状态机（P0 地基）

> 先定这两样，再写一行代码。表结构决定能做什么，状态机决定怎么流转。

---

## 一、表清单（P0 共 8 张）

| 表 | 作用 | 关键点 |
|---|---|---|
| `user` | 玩家 + 管理员 | 三类角色统一入口 |
| `adventurer` | 冒险家档案（服务者） | 技能标签、评分、在途单上限 |
| `category` | 委托分类 | 深渊 / 日常 / 材料 / 咨询 |
| `service_item` | 委托模板（可下单的服务项） | 价格会变，所以订单要存快照 |
| `commission` | 委托单（核心表） | 状态机 + 超时字段 |
| `commission_item` | 委托明细 | **价格快照**，不能只存外键 |
| `payment` | 支付流水 | `out_trade_no` 唯一索引 = 幂等的物理保障 |
| `commission_log` | 状态流转日志 | 审计 + 排障 + 测试数据来源 |

P1 再加：`settlement`（结算）、`dispute`（争议）、`account`（余额流水）。

---

## 二、DDL

> MySQL 8，字符集 `utf8mb4`。直接拿去跑，别手抄漏字段。

```sql
-- 1. 用户（玩家/管理员，冒险家另建档案表）
CREATE TABLE `user` (
  `id`         BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `phone`      VARCHAR(20)  NOT NULL COMMENT '登录手机号',
  `nickname`   VARCHAR(50)  NOT NULL,
  `avatar`     VARCHAR(255) NOT NULL DEFAULT '',
  `role`       VARCHAR(20)  NOT NULL DEFAULT 'player' COMMENT 'player / admin',
  `status`     TINYINT      NOT NULL DEFAULT 1 COMMENT '1正常 0禁用',
  `created_at` DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_phone` (`phone`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 冒险家档案
CREATE TABLE `adventurer` (
  `id`               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `user_id`          BIGINT UNSIGNED NOT NULL,
  `game_uid`         VARCHAR(20)  NOT NULL COMMENT '原神 UID',
  `server`           VARCHAR(20)  NOT NULL COMMENT '天空岛 / 世界树',
  `game_nickname`    VARCHAR(50)  NOT NULL,
  `skill_tags`       JSON         NULL COMMENT '["深渊","日常"]',
  `rating`           DECIMAL(3,2) NOT NULL DEFAULT 5.00,
  `finished_count`   INT          NOT NULL DEFAULT 0,
  `abandoned_count`  INT          NOT NULL DEFAULT 0,
  `max_concurrent`   INT          NOT NULL DEFAULT 3 COMMENT '同时在途单上限',
  `audit_status`     VARCHAR(20)  NOT NULL DEFAULT 'pending' COMMENT 'pending/approved/rejected',
  `online_status`    VARCHAR(20)  NOT NULL DEFAULT 'offline' COMMENT 'online/offline',
  `created_at`       DATETIME     NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_user` (`user_id`),
  UNIQUE KEY `uk_game_uid` (`game_uid`, `server`),
  KEY `idx_dispatch` (`audit_status`, `online_status`, `rating`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 委托分类
CREATE TABLE `category` (
  `id`     INT UNSIGNED NOT NULL AUTO_INCREMENT,
  `name`   VARCHAR(30)  NOT NULL,
  `sort`   INT          NOT NULL DEFAULT 0,
  `status` TINYINT      NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_name` (`name`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 委托模板（服务项）
CREATE TABLE `service_item` (
  `id`           BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `category_id`  INT UNSIGNED    NOT NULL,
  `name`         VARCHAR(80)     NOT NULL COMMENT '如：深渊12层满星（含配队）',
  `description`  TEXT            NULL,
  `price`        DECIMAL(10,2)   NOT NULL,
  `duration_min` INT             NOT NULL DEFAULT 60 COMMENT '预计分钟数',
  `status`       TINYINT         NOT NULL DEFAULT 1 COMMENT '1上架 0下架',
  `created_at`   DATETIME        NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_cat_status` (`category_id`, `status`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. 委托单（核心）
CREATE TABLE `commission` (
  `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `order_no`        VARCHAR(32)   NOT NULL COMMENT '业务单号，对外展示',
  `player_id`       BIGINT UNSIGNED NOT NULL,
  `adventurer_id`   BIGINT UNSIGNED NULL COMMENT '抢单成功后写入',
  `game_uid`        VARCHAR(20)   NOT NULL COMMENT '接单方要加的 UID',
  `server`          VARCHAR(20)   NOT NULL,
  `expect_time`     DATETIME      NULL COMMENT '期望完成时间',
  `total_amount`    DECIMAL(10,2) NOT NULL,
  `status`          VARCHAR(20)   NOT NULL DEFAULT '待支付',
  `remark`          VARCHAR(255)  NOT NULL DEFAULT '',
  `pay_deadline`    DATETIME      NOT NULL COMMENT '支付截止（下单 +30min）',
  `accept_deadline` DATETIME      NULL COMMENT '验收截止（交付时写入）',
  `paid_at`         DATETIME      NULL,
  `accepted_at`     DATETIME      NULL,
  `finished_at`     DATETIME      NULL,
  `settled_at`      DATETIME      NULL,
  `pool_retry`      INT           NOT NULL DEFAULT 0 COMMENT '回池次数',
  `version`         INT           NOT NULL DEFAULT 0,
  `created_at`      DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_order_no` (`order_no`),
  KEY `idx_hall`          (`status`, `created_at`),
  KEY `idx_player`        (`player_id`, `created_at`),
  KEY `idx_adventurer`    (`adventurer_id`, `status`),
  KEY `idx_pay_timeout`   (`status`, `pay_deadline`),
  KEY `idx_accept_timeout`(`status`, `accept_deadline`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. 委托明细（价格快照）
CREATE TABLE `commission_item` (
  `id`              BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `commission_id`   BIGINT UNSIGNED NOT NULL,
  `service_item_id` BIGINT UNSIGNED NOT NULL,
  `snapshot_name`   VARCHAR(80)   NOT NULL COMMENT '下单时的服务名',
  `snapshot_price`  DECIMAL(10,2) NOT NULL COMMENT '下单时的价格',
  `quantity`        INT           NOT NULL DEFAULT 1,
  PRIMARY KEY (`id`),
  KEY `idx_commission` (`commission_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. 支付流水
CREATE TABLE `payment` (
  `id`               BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `commission_id`    BIGINT UNSIGNED NOT NULL,
  `out_trade_no`     VARCHAR(32)   NOT NULL COMMENT '外部交易号（幂等键）',
  `amount`           DECIMAL(10,2) NOT NULL,
  `channel`          VARCHAR(20)   NOT NULL DEFAULT 'mock',
  `status`           VARCHAR(20)   NOT NULL DEFAULT 'pending' COMMENT 'pending/success/failed/refunded',
  `callback_payload` JSON          NULL COMMENT '原始回调，排障用',
  `paid_at`          DATETIME      NULL,
  `created_at`       DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  UNIQUE KEY `uk_out_trade_no` (`out_trade_no`),
  KEY `idx_commission` (`commission_id`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. 状态流转日志
CREATE TABLE `commission_log` (
  `id`            BIGINT UNSIGNED NOT NULL AUTO_INCREMENT,
  `commission_id` BIGINT UNSIGNED NOT NULL,
  `from_status`   VARCHAR(20)   NOT NULL,
  `to_status`     VARCHAR(20)   NOT NULL,
  `event`         VARCHAR(30)   NOT NULL COMMENT '触发事件名',
  `operator_id`   BIGINT UNSIGNED NULL,
  `operator_role` VARCHAR(20)   NOT NULL DEFAULT 'system' COMMENT 'player/adventurer/admin/system',
  `created_at`    DATETIME      NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (`id`),
  KEY `idx_commission` (`commission_id`, `created_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
```

---

## 三、六个设计决策（每个都会在面试被问）

### 1. 订单明细必须存价格快照

`commission_item` 里有 `snapshot_name`、`snapshot_price`，而不是只存 `service_item_id`。

**为什么**：服务项价格随时会改。如果订单只存外键，玩家三个月后翻订单，看到的是**现在的价格**，不是他当时付的钱。财务上这是错的。

**面试话术**：「订单明细存快照，因为商品价格会变，订单是历史事实，不能被后来的修改影响。」

### 2. 支付幂等靠唯一索引，不靠锁

`payment.out_trade_no` 建唯一索引。支付回调重复到达时，第二次插入直接抛 `IntegrityError`，捕获后返回「已处理」，不重复入账。

**为什么不用 Redis 锁**：锁有超时、有失效窗口，而唯一索引是数据库的强约束，**一次写成，永远生效**。能用约束解决的问题不要用锁。

**这也回答了一个常见追问**：订单状态更新要不要幂等？要，但用状态机判断（`待支付` 才能变 `待接单`），不需要额外机制。

### 3. 超时用绝对时间字段，不靠任务算

`pay_deadline`、`accept_deadline` 在**写状态时就算好**。定时任务只做一件事：`SELECT ... WHERE status='待支付' AND pay_deadline < NOW()`。

**为什么不在任务里算 `created_at + 30min`**：算出来的条件和索引对不上，全表扫描。存绝对时间才能吃 `idx_pay_timeout` 索引。

### 4. 金额用 DECIMAL，永远不用 FLOAT

DECIMAL(10,2)，最大 9999 万，两位小数。浮点数存钱会出现 `0.1 + 0.2 = 0.30000000000000004`，对账时永远平不了。

### 5. 抢单用数据库 CAS，Redis 锁是第二层

核心写法：

```sql
UPDATE commission
SET adventurer_id = ?, status = '进行中', accepted_at = NOW()
WHERE id = ? AND status = '待接单' AND adventurer_id IS NULL
```

看 `rowcount`：`1` 就是抢到，`0` 就是被别人抢先。

**这是数据库层面的 CAS，本身已经是原子的。** 那 Redis 锁还有什么用？——**减少无效的数据库写入竞争**（20 个请求同时打进来，19 个在锁那层就被挡掉，不用都去 DB 转一圈）。两层都要，但要知道谁是真保障、谁是性能优化。这个区分面试很加分。

### 6. 状态日志单独一张表

每次状态变更写一条 `commission_log`。作用有三个：
- 出问题时能还原「这单为什么卡在这」，不用猜
- 争议仲裁时的客观依据
- **状态机测试的断言依据**（跑完一个流程，检查日志是不是预期的序列）

---

## 四、状态机

### 状态定义（9 个）

| 状态 | 含义 | 谁来推动 |
|---|---|---|
| `待支付` | 下单成功，等付款 | 玩家 |
| `待接单` | 已付款，进委托大厅 | 冒险家抢单 / 系统回池 |
| `进行中` | 有人接了，正在做 | 冒险家 |
| `待验收` | 已交付，等玩家确认 | 玩家 / 系统超时 |
| `已完成` | 玩家确认，等结算 | 系统 |
| `已结算` | 钱已入账，终态 | 系统 |
| `已关闭` | 未支付超时 / 主动取消 | 系统 / 玩家 |
| `已取消` | 已支付但未完成（退款） | 玩家 / 冒险家弃单 |
| `争议中` | 有待仲裁的纠纷 | 玩家 / 冒险家 |

### 转移表（纯数据，不是 if-else）

```python
# 状态常量
PENDING_PAY    = "待支付"
PENDING_ACCEPT = "待接单"
IN_PROGRESS    = "进行中"
PENDING_VERIFY = "待验收"
COMPLETED      = "已完成"
SETTLED        = "已结算"
CLOSED         = "已关闭"
CANCELED       = "已取消"
DISPUTING      = "争议中"

# (当前状态, 事件) -> 目标状态
TRANSITIONS: dict[tuple[str, str], str] = {
    # 支付阶段
    (PENDING_PAY,    "支付成功"):     PENDING_ACCEPT,
    (PENDING_PAY,    "支付超时"):     CLOSED,
    (PENDING_PAY,    "玩家取消"):     CLOSED,

    # 接单阶段
    (PENDING_ACCEPT, "抢单成功"):     IN_PROGRESS,
    (PENDING_ACCEPT, "超时无人接"):   PENDING_ACCEPT,   # 自转移：仅累加 pool_retry + 写日志
    (PENDING_ACCEPT, "玩家取消"):     CANCELED,

    # 履约阶段
    (IN_PROGRESS,    "提交交付"):     PENDING_VERIFY,
    (IN_PROGRESS,    "冒险家弃单"):   CANCELED,

    # 验收阶段
    (PENDING_VERIFY, "玩家确认"):     COMPLETED,
    (PENDING_VERIFY, "验收超时"):     COMPLETED,        # 自动确认
    (PENDING_VERIFY, "玩家申诉"):     DISPUTING,

    # 结算与售后
    (COMPLETED,      "结算"):         SETTLED,
    (COMPLETED,      "7天内申诉"):    DISPUTING,

    # 争议
    (DISPUTING,      "判定完成"):     COMPLETED,
    (DISPUTING,      "判定退款"):     CANCELED,
    (DISPUTING,      "部分退款"):     COMPLETED,        # 退一部分，剩余结算
}

class IllegalTransition(Exception):
    """非法状态转移 —— 业务异常，返回 409"""
```

**16 条合法转移，15 个不同事件。** 剩下的组合全是非法，例如：

| 非法转移 | 说明什么 |
|---|---|
| `待支付` → `进行中` | 跳过支付，白嫖 |
| `已关闭` → `待接单` | 关掉的单被复活 |
| `已取消` → `进行中` | 退款后还能做 |
| `已完成` → `待支付` | 状态回退 |
| `待接单` → `已结算` | 没交付就结算 |

**测试规模**：9 状态 × 15 事件 = **135 种组合**，其中 16 条合法、**119 条非法**。这 119 条就是你的参数化测试用例（`pytest.mark.parametrize` 一行跑完）。

### transition 函数签名

```python
async def transition(
    db, commission_id: int, event: str,
    operator_id: int | None = None,
    operator_role: str = "system",
    **extra,                      # 如 pool_retry 增量、accept_deadline
) -> str:
    """当前状态 + 事件 -> 新状态；非法则抛 IllegalTransition。"""
```

三件事必须原子：**改状态 + 写日志 + 落 extra 字段**，同一个事务。

---

## 五、目录骨架（你自己建）

```
teyvat-guild/
  app/
    main.py
    config.py
    db.py                 # engine + session
    models/               # SQLAlchemy 模型，一张表一个文件
      user.py adventurer.py category.py service_item.py
      commission.py commission_item.py payment.py commission_log.py
    schemas/              # Pydantic 出入参
    core/
      state_machine.py    # TRANSITIONS + transition()
      exceptions.py       # IllegalTransition / BizError
      security.py         # JWT
    services/
      commission_service.py
      payment_service.py
      dispatch_service.py
    routers/
      commission.py payment.py adventurer.py hall.py
    tasks/
      timeouts.py         # 关单 / 回池 / 自动验收
  tests/
    test_state_machine.py # 135 种组合
    test_commission_flow.py
  scripts/
    seed.py               # 造一批分类/服务项/冒险家
```

---

## 六、P0 验收标准

跑通这一条，P0 就完成：

```
造 1 个玩家、1 个冒险家、1 个服务项
→ 玩家下单（待支付）
→ 调支付回调（待接单）
→ 冒险家抢单（进行中）
→ 提交交付（待验收）
→ 玩家确认（已完成）
→ 结算（已结算）
→ 查 commission_log，看到 6 条按顺序的流转记录
```

同时 `pytest tests/test_state_machine.py` 全绿（135 种组合）。
