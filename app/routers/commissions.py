from fastapi import APIRouter, Depends, Header,HTTPException
from app.db import get_db
from app.core.exceptions import BizError
from app.services import commission_service
from app.schemas.commission import OrderCreateIn

router = APIRouter(prefix="/commissions",tags=["委托"])

async def fake_current_player(x_player_id: int = Header(...)):
    """假鉴权：从请求头拿 player_id。真 JWT 登录后替换这个依赖。"""
    return x_player_id
@router.post("")
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
    return {"order_no": order.order_no, "total_amount": str(order.total_amount)}