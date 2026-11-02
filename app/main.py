import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import settings
from app.db import engine
from app.routers import commissions
from app.tasks.timeout_scanner import scan_once

logger = logging.getLogger(__name__)

async def _timeout_loop() -> None:
    """先跑一轮再睡：重启后立刻清理积压，不用等一个周期。"""
    while True:
        try:
            stats = await scan_once()
            if any(stats.values()):
                logger.info("timeout scan: %s", stats)
        except asyncio.CancelledError:
            raise # 关停信号必须往上抛，否则任务取消不掉
        except Exception:
            logger.exception("timeout scan failed") # 一单炸了不能拖死整轮
        await asyncio.sleep(settings.scan_interval_sec)

@asynccontextmanager
async def lifespan(app: FastAPI):
    # 引用必须持有：只 create_task 不存引用，任务可能被 GC 掉
    app.state.timeout_task = asyncio.create_task(_timeout_loop())
    try:
        yield
    finally:
        app.state.timeout_task.cancel()
        try:
            await app.state.timeout_task # cancel 后必须 await，否则任务泄漏
        except asyncio.CancelledError:
            pass
        await engine.dispose()
app = FastAPI(title="Teycat Guild", lifespan=lifespan)
app.include_router(commissions.router)
@app.get("/")
async def root():
    return {"status": "ok", "service": "teyvat-guild"}
