"""订单状态机 —— 转移表是纯数据，业务代码里不许再出现 if status == ..."""

PENDING_PAY = "待支付"
PENDING_ACCEPT = "待接单"
IN_PROGRESS = "进行中"
PENDING_VERIFY = "待验收"
COMPLETED = "已完成"
SETTLED = "已结算"
CLOSED = "已关闭"
CANCELED = "已取消"
DISPUTING = "争议中"

ALL_STATES = [PENDING_PAY, PENDING_ACCEPT, IN_PROGRESS, PENDING_VERIFY,
              COMPLETED, SETTLED, CLOSED, CANCELED, DISPUTING]

TRANSITIONS: dict[tuple[str,str], str] = {
    (PENDING_PAY, "支付成功"): PENDING_ACCEPT,
    (PENDING_PAY, "支付超时"): CLOSED,
    (PENDING_PAY, "玩家取消"): CLOSED,
    (PENDING_ACCEPT, "抢单成功"): IN_PROGRESS,
    (PENDING_ACCEPT, "超时无人接"): PENDING_ACCEPT, # 自转移: 只累加pool_retry
    (PENDING_ACCEPT, "玩家取消"): CANCELED,
    (IN_PROGRESS, "提交交付"): PENDING_VERIFY,
    (IN_PROGRESS, "冒险家弃单"): CANCELED,
    (PENDING_VERIFY, "玩家确认"): COMPLETED,
    (PENDING_VERIFY, "验收超时"): COMPLETED,
    (PENDING_VERIFY, "玩家申诉"): DISPUTING,
    (COMPLETED, "结算"): SETTLED,
    (COMPLETED, "7天内申诉"): DISPUTING,
    (DISPUTING, "判定完成"): COMPLETED,
    (DISPUTING, "判定退款"): CANCELED,
    (DISPUTING, "部分退款"): COMPLETED,
}

EVENTS = sorted({e for _, e in TRANSITIONS})

class IllegalTranstition(Exception):
    def __init__(self, from_status: str, event: str):
        self.from_status, self.event = from_status, event
        super().__init__(f"非法转移:{from_status} -- [{event}]--> ?")

def next_status(current: str, event: str) -> str:
    """纯函数，不碰 DB，所以 135 种组合能毫秒级穷举。"""
    target = TRANSITIONS.get((current,event))
    if target is None:
        raise IllegalTranstition(current,event)
    return target