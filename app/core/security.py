"""密码哈希与 JWT 签发/校验。

为什么不能明文存、也不能用 md5/sha256：
- 明文：库泄露 = 所有账号泄露
- md5/sha256：算得太快，GPU 每秒几十亿次，彩虹表挡不住
- bcrypt 故意慢（默认 12 轮 ≈ 0.3s/次），且每次自动生成随机盐
"""
import bcrypt
import jwt
from datetime import timedelta

from app.config import settings
from app.core.time_utils import utcnow

def hash_password(plain: str) -> str:
     """明文 → 可直接入库的哈希串。盐自动生成并内嵌在结果里。"""
     if not plain:
          raise ValueError("密码不能为空")
     if len(plain.encode("utf-8")) > 72:
          raise ValueError("密码过长") # bcrypt 只认前 72 字节，超出会静默截断
     return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt()).decode("ascii")

def verify_password(plain: str, hashed: str) -> bool:
     """校验密码。空串/非法格式的哈希必须返回 False，不能崩。"""
     if not hashed or not plain:
          return False
     try:
          return bcrypt.checkpw(plain.encode("utf-8"), hashed.encode("ascii"))
     except (ValueError, UnicodeEncodeError):
          return False # 哈希格式非法也当"不匹配"，异常不外抛

def create_access_token(user_id: int, role: str) ->str:
     payload = {
          "sub": str(user_id), # JWT 规范：sub 必须是字符串
          "role": role,
          "iat": utcnow(),
          "exp": utcnow() + timedelta(minutes=settings.jwt_expire_minutes),
     }
     return jwt.encode(payload, settings.jwt_secret,
                       algorithm=settings.jwt_algorithm)

def decode_access_token(token: str) -> dict:
     """过期/签名不符/格式错都抛 jwt.PyJWTError，由依赖层统一转 401。"""
     return jwt.decode(token, settings.jwt_secret,
                       algorithms=[settings.jwt_algorithm])