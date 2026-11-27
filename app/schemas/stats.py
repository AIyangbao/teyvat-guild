"""管理端统计看板的响应结构。所有金额用 Decimal，不用 float —— 钱不能有精度误差。"""
from decimal import Decimal
from pydantic import BaseModel

class DailyTrend(BaseModel):
    """单日趋势点。date 是字符串 YYYY-MM-DD，前端直接当 X 轴标签。"""
    date: str
    amount: Decimal # 当日成功支付金额
    orders: int


class StatusSlice(BaseModel):
    name: str
    count: int

class ServerSlice(BaseModel):
    name: str
    count: int
    amount: Decimal

class TopAdventurer(BaseModel):
    adventurer_id: int
    game_nickname: str
    finished_count: int
    rating: Decimal
    review_count: int

class StatsOverviewOut(BaseModel):
    # 四个 KPI
    total_revenue: Decimal       # 累计成功支付金额
    total_orders: int            # 累计委托数（含未支付）
    paid_orders: int             # 成功支付单数
    avg_rating: Decimal | None   # 全站评价均分；无评价时 None，前端显示「暂无]
    # 四个分布
    trend: list[DailyTrend]
    status_breakdown: list[StatusSlice]
    server_breakdown: list[ServerSlice]
    top_adventurers: list[TopAdventurer]