from functools import lru_cache
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_host: str = "127.0.0.1"
    db_port: int = 3306
    db_user: str = "root"
    db_password: str = ""
    db_name: str = "teyvat_guild"
    db_echo: bool = False

    order_pay_timeout_min: int = 30
    order_accept_timeout_min: int = 15
    order_verify_timeout_hours: int = 72
    scan_interval_sec: int = 60   # 扫描器轮询间隔（下一阶段 lifespan 用）
    max_pool_retry: int = 3       # 待接单自转移上限，到顶走「无人接单关闭」
    after_sale_days: int = 7
    # 支付回调验签（模拟环境用共享密钥；真实支付是 MD5/RSA 对 body 签名）
    pay_callback_secret: str = "mock-callback-secret-change-me"


    jwt_secret: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 120

        # Redis（大厅缓存）
    redis_host: str = "127.0.0.1"
    redis_port: int = 6379
    redis_db: int = 0
    redis_password: str = ""

    @property
    def db_url(self) -> str:
        return (f"mysql+aiomysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4")
    @property
    def db_url_sync(self) -> str:
        return (f"mysql+pymysql://{self.db_user}:{self.db_password}"
                f"@{self.db_host}:{self.db_port}/{self.db_name}?charset=utf8mb4")

@lru_cache
def get_settings() -> Settings:
    return Settings()

settings = get_settings()