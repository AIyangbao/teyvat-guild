"""alembic 运行环境：对接 app 的模型与配置。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))  # 项目根

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool
from alembic import context

from app.config import settings
from app.db import Base
import app.models  # noqa: F401  import 触发 8 张表注册进 Base.metadata

config = context.config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 数据库地址从 app 配置读（.env），不写死在 ini 里
config.set_main_option("sqlalchemy.url", settings.db_url_sync)
# 允许命令行 -x db_url=... 临时切换目标库（生成基线用）
x_args = context.get_x_argument(as_dictionary=True)
if "db_url" in x_args:
    config.set_main_option("sqlalchemy.url", x_args["db_url"])

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：不连库，把迁移编成 SQL 脚本（--sql 时走这里）。"""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,   # 类型变更也能被 autogenerate 识别（默认只看增删）
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连库执行（默认走这里）。"""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
