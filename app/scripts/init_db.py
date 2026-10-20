from sqlalchemy import create_engine, text
from app.config import settings
from app.db import Base
import app.models
# 先建库（连到不带库名的地址）
server_url = f"mysql+pymysql://{settings.db_user}:{settings.db_password}@{settings.db_host}:{settings.db_port}/?charset=utf8mb4"
eng = create_engine(server_url)
with eng.connect() as c:
    c.execute(text(f"CREATE DATABASE IF NOT EXISTS `{settings.db_name}` DEFAULT CHARSET utf8mb4"))
    c.commit()
eng.dispose()


# 再建表
sync_engine = create_engine(settings.db_url_sync)
Base.metadata.create_all(sync_engine)
print("建表完成")