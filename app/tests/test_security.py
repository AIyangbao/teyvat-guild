"""core/security 单测。纯函数，无 db fixture。"""
from datetime import timedelta

import pytest
import jwt as pyjwt

from app.config import settings
from app.core.time_utils import utcnow
from app.core.security import (
    create_access_token, decode_access_token, hash_password, verify_password,
)

class TestPassword:
    def test_hash_and_verify_roundtrip(self):
        hashed = hash_password("s3cret-pw")
        assert hashed != "s3cret-pw" # 不是明文
        assert hashed.startswith("$2")  # bcrypt 格式
        assert verify_password("s3cret-pw", hashed) is True

    def test_wrong_password_rejected(self):
        hashed = hash_password("s3cret-pw")
        assert verify_password("wrong", hashed) is False

    def test_salt_makes_hashes_differ(self):
        """同一密码两次哈希不同（随机盐），但都能通过校验。"""
        h1 = hash_password("same-pw")
        h2 = hash_password("same-pw")
        assert h1 != h2
        assert verify_password("same-pw", h1)
        assert verify_password("same-pw", h2)

    def test_empty_or_garbage_hash_rejected(self):
        """历史空串/非法格式不能崩，只能 False。"""
        assert verify_password("any", "") is False
        assert verify_password("any", "not-a-bcrypt-hash") is False

    def test_empty_password_rejected(self):
        with pytest.raises(ValueError):
            hash_password("")

class TestToken:
    def test_roundtrip_carries_identity(self):
        token = create_access_token(42,"player")
        claims = decode_access_token(token)
        assert claims["sub"] == "42"
        assert claims["role"] == "player"

    def test_tampered_token_rejected(self):
        token = create_access_token(42, "player")
        bogus = token[:-4] + "xxxx"
        with pytest.raises(pyjwt.PyJWTError):
            decode_access_token(bogus)

    def test_expired_token_rejected(self):
        claims = {"sub": "42", "role": "player",
                  "exp": utcnow() - timedelta(minutes=1)}
        token = pyjwt.encode(claims, settings.jwt_secret,
                             algorithm=settings.jwt_algorithm)
        with pytest.raises(pyjwt.ExpiredSignatureError):
            decode_access_token(token)