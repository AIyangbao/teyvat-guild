"""用户自己资料：只见自己、只改自己。身份来自 token，不收 user_id 参数。"""
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_current_user
from app.core.exceptions import BizError
from app.db import DB
from app.models import Adventurer, User
from app.schemas.user import ProfileOut, ProfileUpdate, AdventurerUpdate
from app.services import storage_service, user_service

router = APIRouter(prefix="/users", tags=["users"])
_STATUS = {
    "FILE_TOO_LARGE": 413,
    "FILE_TYPE_INVALID": 415,
    "ROLE_FORBIDDEN": 403,
}

def _fail(e: BizError):
    raise HTTPException(status_code=_STATUS.get(e.code, 400),
                        detail={"code": e.code, "message": str(e)})

@router.get("/me", response_model=ProfileOut)
async def my_profile(user: User = Depends(get_current_user), db: AsyncSession = DB):
    return await user_service.get_profile(db, user)

@router.put("/me", response_model=ProfileOut)
async def update_profile(data: ProfileUpdate,
                         user: User = Depends(get_current_user),
                         db: AsyncSession = DB):
    try:
        return await user_service.update_nickname(db, user, data.nickname)
    except BizError as e:
        _fail(e)

@router.post("/me/avatar", response_model=ProfileOut)
async def upload_avatar(file: UploadFile = File(...),
                        user: User = Depends(get_current_user),
                        db: AsyncSession = DB):
    try:
        url = await storage_service.save_avatar(user.id, file)
        return await user_service.set_avatar(db, user, url)
    except BizError as e:
        _fail(e)

@router.put("/adventurers/me", response_model=ProfileOut)
async def update_my_adventurer(data: AdventurerUpdate,
                               user: User = Depends(get_current_user),
                               db: AsyncSession = DB):
    try:
        return await user_service.update_my_adventurer(db, user, data)
    except BizError as e:
        _fail(e)