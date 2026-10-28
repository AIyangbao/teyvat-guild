from fastapi import APIRouter, Depends, Header,HTTPException
from app.db import get_db
from app.core.exceptions import BizError
from app.services import commission_service,commission_state
from app.schemas.commission import OrderCreateIn

router = APIRouter(prefix="/commissions",tags=["委托"])

async def fake_current_player(x_player_id: int = Header(...)):
    """假鉴权：从请求头拿 player_id。真 JWT 登录后替换这个依赖。"""
    return x_player_id
@router.post("/create_order")
async def create_order(data: OrderCreateIn,
                       db=Depends(get_db),
                       player_id: int = Depends(fake_current_player)):
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
async def pay(order_id: int, db=Depends(get_db), player_id: int = Depends(fake_current_player)):
    try:
        order = await commission_state.transition(db, order_id, "支付成功",
                                                  operator_id=player_id, operator_role="player")
    except BizError as e:
        status = 409 if e.code == "STATE_ILLEGAL" else (404 if e.code == "ORDER_NOT_FOUND" else 400)
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})

async def fake_current_adventurer(x_adventurer_id: int = Header(...)) -> int:
     """假鉴权：真 JWT 后替换。"""
     return x_adventurer_id

@router.post("/{order_id}/accept")
async def aacept(order_id: int,
                 db=Depends(get_db),
                 adventurer_id: int = Depends(fake_current_adventurer)):
    try:
        order = await commission_state.accept_order(db, order_id, adventurer_id)
    except BizError as e:
        status = 409 if e.code == "ACCEPT_CONFLICT" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})
    return {"order_no": order.order_no, "status": order.status,
            "adventurer_id": order.adventurer_id}
    