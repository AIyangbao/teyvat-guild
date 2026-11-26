from fastapi import APIRouter, Depends,  Query, HTTPException
from app.db import DB
from app.core.exceptions import BizError
from app.services import (commission_service,commission_state, payment_service,
                           recommend_service,review_service)
from app.schemas.recommend import RecommendationOut
from app.schemas.commission import OrderCreateIn, HallPageOut, CommissionDetailOut
from app.schemas.payment import PayCreateOut
from app.schemas.review import ReviewIn, ReviewOut, ReviewReadOut
from app.core.deps import get_current_adventurer, get_current_player
router = APIRouter(prefix="/commissions",tags=["委托"])

@router.post("/create_order")
async def create_order(data: OrderCreateIn,
                       db=DB,
                       player_id: int = Depends(get_current_player)):
    try:
        order = await commission_service.create_order(
            db, player_id,
            item_inputs=[i.model_dump() for i in data.items],
            game_uid=data.game_uid, server=data.server,
            expect_time=data.expect_time, remark=data.remark,
        )
    except BizError as e:
        raise HTTPException(status_code=400,detail={"code":e.code,"message":str(e)})
    return {"order_id": order.id,"order_no": order.order_no, "total_amount": str(order.total_amount)}

@router.post("/{order_id}/pay")
async def pay(order_id: int, db=DB, player_id: int = Depends(get_current_player)):
    try:
        p = await payment_service.create_payment(db, order_id, player_id)
    except BizError as e:
        status = (404 if e.code == "ORDER_NOT_FOUND"
                  else 403 if e.code == "FORBIDDEN"
                  else 409 if e.code in ("STATE_ILLEGAL", "PAY_EXPIRED")
                  else 400)
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})
    return PayCreateOut(out_trade_no=p.out_trade_no,
                        amount=str(p.amount), channel=p.channel)


@router.post("/{order_id}/accept")
async def aacept(order_id: int,
                 db=DB,
                 adventurer_id: int = Depends(get_current_adventurer)):
    try:
        order = await commission_state.accept_order(db, order_id, adventurer_id)
    except BizError as e:
        status = (409 if e.code in ("STATE_ILLEGAL", "ACCEPT_CONFLICT") 
                  else 404 if e.code == "ORDER_NOT_FOUND" 
                  else 403 if e.code in ("FORBIDDEN", "ADVENTURER_NOT_APPROVED")
                  else 400)
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})
    return {"order_no": order.order_no, "status": order.status,
            "adventurer_id": order.adventurer_id}

@router.post("/{order_id}/deliver")
async def deliver(order_id: int, db=DB,
                  adventurer_id: int = Depends(get_current_adventurer)):
    try:
        order = await commission_state.deliver_by_adventurer(db, order_id, adventurer_id)
    except BizError as e:
        status = (409 if e.code == "STATE_ILLEGAL" 
                  else 404 if e.code == "ORDER_NOT_FOUND" 
                  else 403 if e.code == "FORBIDDEN"
                  else 400)
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})
    return {"order_id": order.id, "status": order.status}

@router.post("/{order_id}/confirm")
async def confirm(order_id: int, db= DB, player_id: int = Depends(get_current_player)):

    try:
        order = await commission_state.confirm_by_player(db, order_id, player_id)
    except BizError as e:
        status = (409 if e.code == "STATE_ILLEGAL" 
                  else 404 if e.code == "ORDER_NOT_FOUND" 
                  else 403 if e.code == "FORBIDDEN"
                  else 400)
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})
    return {"order_id": order.id, "status": order.status}

@router.get("/hall", response_model=HallPageOut)
async def hall(page: int = Query(1, ge=1),
               page_size: int = Query(20, ge=1, le=50),
               db=DB):
    """委托大厅：公开接口，不需要登录头。"""
    total, rows = await commission_service.list_hall(db, page, page_size)
    return HallPageOut(total=total, items=rows)

@router.get("/mine", response_model=HallPageOut)
async def my_orders(page: int = Query(1, ge=1),
                    page_size: int = Query(20, ge=1, le=50),
                    status: str | None = Query(None),
                    db=DB,
                    player_id: int = Depends(get_current_player)):
    try:
        total, rows = await commission_service.list_mine(
            db, player_id, page, page_size, status)
    except BizError as e:
        raise HTTPException(status_code=400,
                            detail={"code": e.code, "message": str(e)})
    return HallPageOut(total=total, items=rows)

@router.get("/accepted", response_model=HallPageOut)
async def accepted_orders(page: int = Query(1, ge=1),
                          page_size: int = Query(20, ge=1, le=50),
                          status: str | None = Query(None),
                          db=DB,
                          adventurer_id: int = Depends(get_current_adventurer)):
    """冒险家侧：我接的委托（可按状态过滤：进行中/已完成/已结算…）。"""
    try:
        total, rows = await commission_service.list_by_adventurer(
            db, adventurer_id, page, page_size, status)
    except BizError as e:
        status = (409 if e.code in ("STATE_ILLEGAL", "ACCEPT_CONFLICT")
                  else 404 if e.code == "ORDER_NOT_FOUND"
                  else 403 if e.code in ("FORBIDDEN", "ADVENTURER_NOT_APPROVED")
                  else 400)
        raise HTTPException(status_code=status,
                            detail={"code":e.code, "message": str(e)})
    return HallPageOut(total=total, items=rows)

@router.get("/{order_id}/review", response_model=ReviewReadOut | None)
async def get_review(order_id: int, db=DB):
     """详情页刷新用：没有评价返回 200 + null，不弹红色报错。"""
     return await review_service.get_review_by_order(db, order_id)

@router.get("/{order_id}", response_model=CommissionDetailOut)
async def detail(order_id: int, db=DB):
    try:
        return await commission_service.get_detail(db, order_id)
    except BizError as e:
        status = 404 if e.code == "ORDER_NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})
    
@router.get("/{order_id}/recommendations", response_model=list[RecommendationOut])
async def recommend_adventurers(
    order_id: int,
    limit: int = Query(5, ge=1, le=20),
    db=DB,
):
  """只读推荐：给定委托，返回 Top N 合适冒险家（含分数拆解）。"""
  return await recommend_service.recommend_for_order(db, order_id, limit)

@router.post("/{order_id}/review", response_model=ReviewOut)
async def create_review(order_id: int, data:ReviewIn, db=DB,
                        player_id: int = Depends(get_current_player)):
    try:
        review, rating = await review_service.create_review(
            db, order_id, player_id, data.score, data.content)
    except BizError as e:
        status = (409 if e.code in ("REVIEW_STATE_ILLEGAL", "REVIEW_EXISTS")
                  else 404 if e.code == "ORDER_NOT_FOUND"
                  else 403 if e.code == "FORBIDDEN"
                  else 400)
        raise HTTPException(status_code=status,
                            detail={"code": e.code, "message": str(e)})
    return ReviewOut(
        id=review.id, commission_id=review.commission_id, score=review.score,
        content=review.content, created_at=review.created_at,
        adventurer_rating=rating,
    )