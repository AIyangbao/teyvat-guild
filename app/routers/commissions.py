from fastapi import APIRouter, Depends,  Query, HTTPException
from app.db import get_db
from app.core.exceptions import BizError
from app.services import commission_service,commission_state
from app.schemas.commission import OrderCreateIn, HallPageOut, CommissionDetailOut
from app.core.deps import get_current_adventurer, get_current_player
router = APIRouter(prefix="/commissions",tags=["委托"])

@router.post("/create_order")
async def create_order(data: OrderCreateIn,
                       db=Depends(get_db),
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
async def pay(order_id: int, db=Depends(get_db), player_id: int = Depends(get_current_player)):
    try:
        order = await commission_state.transition(db, order_id, "支付成功",
                                                  operator_id=player_id, operator_role="player")
    except BizError as e:
        status = 409 if e.code == "STATE_ILLEGAL" else (404 if e.code == "ORDER_NOT_FOUND" else 400)
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})
    return {"order_id": order.id, "status": order.status}


@router.post("/{order_id}/accept")
async def aacept(order_id: int,
                 db=Depends(get_db),
                 adventurer_id: int = Depends(get_current_adventurer)):
    try:
        order = await commission_state.accept_order(db, order_id, adventurer_id)
    except BizError as e:
        status = (409 if e.code == "STATE_ILLEGAL" 
                  else 404 if e.code == "ORDER_NOT_FOUND" 
                  else 403 if e.code == "FORBIDDEN"
                  else 400)
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})
    return {"order_no": order.order_no, "status": order.status,
            "adventurer_id": order.adventurer_id}

@router.post("/{order_id}/deliver")
async def deliver(order_id: int, db=Depends(get_db),
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
async def confirm(order_id: int, db= Depends(get_db), player_id: int = Depends(get_current_player)):

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
               db=Depends(get_db)):
    """委托大厅：公开接口，不需要登录头。"""
    total, rows = await commission_service.list_hall(db, page, page_size)
    return HallPageOut(total=total, items=rows)

@router.get("/mine", response_model=HallPageOut)
async def my_orders(page: int = Query(1, ge=1),
                    page_size: int = Query(20, ge=1, le=50),
                    status: str | None = Query(None),
                    db=Depends(get_db),
                    player_id: int = Depends(get_current_player)):
    try:
        total, rows = await commission_service.list_mine(
            db, player_id, page, page_size, status)
    except BizError as e:
        raise HTTPException(status_code=400,
                            detail={"code": e.code, "message": str(e)})
    return HallPageOut(total=total, items=rows)

@router.get("/{order_id}", response_model=CommissionDetailOut)
async def detail(order_id: int, db=Depends(get_db)):
    try:
        return await commission_service.get_detail(db, order_id)
    except BizError as e:
        status = 404 if e.code == "ORDER_NOT_FOUND" else 400
        raise HTTPException(status_code=status, detail={"code": e.code, "message": str(e)})