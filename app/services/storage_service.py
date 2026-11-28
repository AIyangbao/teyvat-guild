"""本地文件存储：头像专用。文件名由服务端生成，不接受客户端路径。"""
from pathlib import Path

from app.core.exceptions import BizError

# 项目根/data/avatars —— 与 README 的 nginx /avatars/ 静态映射对应
AVATAR_DIR =  Path(__file__).resolve().parent.parent.parent / "data" / "avatars"
MAX_BYTES = 2 * 1024 * 1024 # 2MB

# 扩展名 → 文件头魔数。Content-Type 可伪造，魔数骗不了
_SIGNATURES = {
    "jpg": (b"\xff\xd8\xff",),
    "png": (b"\x89PNG\r\n\x1a\n",),
    "webp": (b"RIFF", b"WEBP"),   # WEBP 需同时含两个标记
}

def _detect_ext(data: bytes) -> str | None:
    """只读前 12 字节判断真实格式，返回白名单扩展名。"""
    for ext, sigs in _SIGNATURES.items():
        if ext == "webp":
            if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
                return ext
        elif any(data.startswith(sig) for sig in sigs):
            return ext
    return None

async def save_avatar(user_id: int, upload) -> str:
    """保存头像，返回可供前端拼接的相对 URL。文件覆盖式更新，不留旧文件。"""
    data = await upload.read(MAX_BYTES + 1)
    if len(data) > MAX_BYTES:
        raise BizError("头像不能超过2MB", code="FILE_TOO_LARGE")
    ext = _detect_ext(data)
    if ext is None:
        raise BizError("仅支持 JPG / PNG / WEBP 格式", code="FILE_TYPE_INVALID")

    AVATAR_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{user_id}.{ext}"
    target  = AVATAR_DIR / filename
    target.write_bytes(data)
    return f"/api/avatars/{filename}"