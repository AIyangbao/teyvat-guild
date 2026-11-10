"""鉴权依赖：把 Authorization 头变成可信身份。

依赖链：Bearer 头 → 解 token → 查库验人 → 按角色分支。
约定：401 = 没登录/凭证无效；403 = 登录了但角色不对。
"""
import jwt as pyjwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.security import decode_access_token
from app.db import DB
from app.models import Adventurer, User

# auto_error=False：FastAPI 默认在缺头时抛 403，但我们约定 401，自己控制
_bearer = HTTPBearer(auto_error=False)

def _unauthorized(msg: str) -> HTTPException:
    return HTTPException(status_code=401,
                         detail={"code": "NOT_AUTHENTICATED", "message": msg},
                         headers={"WWW-Authenticate": "Bearer"})

async def get_current_user(
        credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
        db: AsyncSession = DB,
) -> User:
    """所有受保护接口的第一站:token 有效 + 人存在 + 状态正常。"""
    if credentials is None:
        raise _unauthorized("缺少Bearer凭证")
    try:
        claims = decode_access_token(credentials.credentials)
    except pyjwt.PyJWTError:
        raise _unauthorized("凭证无效或已过期")

    user = await db.get(User, int(claims["sub"]))
    if user is None or user.status != 1:
        # token 本身有效，但人已注销/被封 → 必须查库，不能信 token
        raise _unauthorized("账号不存在或已禁用")
    return user

def get_current_player(user: User = Depends(get_current_user)) -> int:
    if user.role != "player":
        raise HTTPException(status_code=403,
                            detail={"code": "ROLE_FORBIDDEN",
                                    "message": "需要玩家身份"})
    return user.id

async def get_current_adventurer(
        user: User = Depends(get_current_user),
        db: AsyncSession = DB,
) -> int:
    if user.role != "adventurer":
        raise HTTPException(status_code=403,
                            detail={"code": "ROLE_FORBIDDEN",
                                    "message": "需要冒险者身份"})
    adv = (await db.execute(
        select(Adventurer.id).where(Adventurer.user_id == user.id)
    )).scalar_one_or_none()
    if adv is None:
        raise HTTPException(status_code=403,
                            detail={"code": "ROLE_FORBIDDEN",
                                    "message": "尚未开通冒险者档案"})
    return adv