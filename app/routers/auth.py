"""注册与登录。注册成功直接发 token，免二次登录。"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError

from app.core.security import create_access_token, hash_password, verify_password
from app.db import DB
from app.models import Adventurer,User
from app.schemas.auth import LoginIn, RegisterIn, TokenOut

router = APIRouter(prefix="/auth", tags=["auth"])

@router.post("/register", response_model=TokenOut, status_code=201)
async def register(data: RegisterIn, db: AsyncSession = DB):
     # 先查重给友好提示；并发正确性由 phone 的 unique 约束兜底
     dup = (await db.execute(
          select(User.id).where(User.phone == data.phone)
     )).scalar_one_or_none()
     if dup is not None:
          raise HTTPException(status_code=409,
                              detail={"code": "PHONE_DUPLICATE",
                                      "message": "手机号已注册"})

     user = User(phone=data.phone, nickname=data.nickname,
                 password_hash=hash_password(data.password), role=data.role)
     db.add(user)
     try:
       await db.flush()
     except IntegrityError:
          raise HTTPException(status_code=409,
                              detail={"code": "PHONE_DUPLICATE",
                                      "message": "手机号已注册"})

     if data.role == "adventurer":
          # 与 User 同一事务：任一步失败，get_db 的 rollback 把两个都撤掉
          adv = Adventurer(
               user_id=user.id,
               game_uid=data.game_uid,
               server=data.server,
               game_nickname=data.game_nickname,
          )
          db.add(adv)
          try:
               await db.flush()
          except IntegrityError:
               # uk_game_uid(game_uid, server) 撞了；并发下的最后防线
               raise HTTPException(status_code=409,
                                   detail={"code": "GAME_UID_DUPLICATE",
                                           "message": "该游戏 UID 已被注册"})

     return TokenOut(access_token=create_access_token(user.id, user.role),
                     user_id=user.id, role=user.role, nickname=user.nickname)

@router.post("/login", response_model=TokenOut)
async def login(data: LoginIn, db: AsyncSession = DB):
     user = (await db.execute(
          select(User).where(User.phone == data.phone)
     )).scalar_one_or_none()
     # 手机号不存在和密码错误给同一句话——不向攻击者透露哪个环节错了
     if user is None or not verify_password(data.password,user.password_hash):
          raise HTTPException(status_code=401,
                              detail={"code": "BAD_CREDENTIALS",
                              "message": "手机号或密码错误"})
     if user.status != 1:
          raise HTTPException(status_code=403,
                              detail={"code": "USER_DISABLED",
                                      "message": "账号已禁用"})
     return TokenOut(access_token=create_access_token(user.id, user.role),
                     user_id=user.id, role=user.role, nickname=user.nickname)
