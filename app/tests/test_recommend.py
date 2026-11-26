"""派单推荐：打分纯函数 + DB 过滤排序。"""
from decimal import Decimal

from app.models import Adventurer
from app.services import commission_service, recommend_service

def test_score_breakdown():
    """手算 87 = 40+20+15+20-8。逐项断言，改权重立刻发现。"""
    score, parts = recommend_service.score_one(
        same_server=True, online=True, rating=Decimal("4.50"),
        review_count=3, finished_count=12, active_count=1)
    assert score == 87
    assert parts.same_server == 40 and parts.online == 20
    assert parts.rating == 15 and parts.experience == 20 and parts.load == -8

def test_no_fake_rating():
    """review_count=0 时 rating=5.00 是模型默认假分，不该加成。"""
    score, parts = recommend_service.score_one(
        same_server=False, online=False, rating=Decimal("5.00"),
        review_count=0, finished_count=0, active_count=0)
    assert parts.rating == 0 and score == 0

def test_load_penalty_and_experience_cap():
    """每单在途扣 8 分；经验封顶 10 单，防止老号无限霸榜。"""
    _, parts = recommend_service.score_one(
        same_server=False, online=False, rating=Decimal("3.00"),
        review_count=1, finished_count=999, active_count=2)
    assert parts.load == -16
    assert parts.experience == 20

async def test_recommend_excludes_pending(db, on_shelf_item, player,
                                          adventurer_row, another_player):
    """已审核的进推荐、同服标记正确；pending 的不进。"""
    pending = Adventurer(
        user_id=another_player.id,
        game_uid="rec_pending_uid",
        server="天空岛",
        game_nickname="待审冒险家",
        audit_status="pending",
    )
    db.add(pending)
    await db.flush()

    order = await commission_service.create_order(
        db, player.id, [{"service_item_id": on_shelf_item.id, "qty": 1}],
        "1", "天空岛")
    recs = await recommend_service.recommend_for_order(db, order.id, 20)

    ids = [r.adventurer_id for r in recs]
    assert adventurer_row.id in ids
    assert pending.id not in ids
    mine = next(r for r in recs if r.adventurer_id == adventurer_row.id)
    assert mine.same_server is True
    assert mine.reasons.same_server == 40