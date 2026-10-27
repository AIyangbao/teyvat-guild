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
    after_sale_days: int = 7

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