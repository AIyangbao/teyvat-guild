from fastapi import FastAPI
from app.routers import commissions
app = FastAPI(title="Teyat Guild")
app.include_router(commissions.router)
@app.get("/")
async def root():
    return {"status": "ok", "service": "teyvat-guild"}
