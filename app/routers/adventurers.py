"""冒险家公开读侧：大厅卡片、档案、评价分页。全部 GET，无需登录。"""
from fastapi import APIRouter, HTTPException, Query

from app.core.exceptions import BizError
from app.db import DB
from app.schemas.adventurer import AdventurerPageOut, AdventurerProfileOut
from app.schemas.review import ReviewPageOut
from app.services import adventurer_service, review_service

router = APIRouter(prefix="/adventurers", tags=["冒险家"])

def _fail(e: BizError):
    raise HTTPException(
        status_code=404 if e.code == "ADVENTURER_NOT_FOUND" else 400,
        detail={"code": e.code, "message": str(e)},
    )


@router.get("",response_model=AdventurerPageOut)
async def list_adventurers(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db=DB,
):
    total, items = await adventurer_service.list_public_adventurers(
        db, page, page_size
    )
    return AdventurerPageOut(total=total, items=items)

@router.get("/{adventurer_id}", response_model=AdventurerProfileOut)
async def profile(adventurer_id: int, db=DB):
    try:
        return await review_service.get_adventurer_profile(db, adventurer_id)
    except BizError as e:
        _fail(e)

@router.get("/{adventurer_id}/reviews", response_model=ReviewPageOut)
async def reviews(
    adventurer_id: int,
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=50),
    db=DB,
):
    try:
        total, items = await review_service.list_reviews_by_adventurer(
            db, adventurer_id, page, page_size)
    except BizError as e:
        _fail(e)
    return ReviewPageOut(total=total, items=items)