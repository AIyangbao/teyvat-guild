#!/bin/sh
# 容器启动流程：等库 → 迁移 → 起服务
# 「容器起 = 结构自动到位」——新环境零手工建表
set -e

echo "[entrypoint] waiting for mysql at ${DB_HOST}:${DB_PORT}..."
until python -c "
import os, pymysql
pymysql.connect(host=os.environ['DB_HOST'], port=int(os.environ['DB_PORT']),
                user=os.environ['DB_USER'], password=os.environ['DB_PASSWORD'],
                database=os.environ['DB_NAME'])
" 2>/dev/null; do
  sleep 1
done

echo "[entrypoint] applying migrations..."
alembic upgrade head

echo "[entrypoint] starting uvicorn..."
exec uvicorn app.main:app --host 0.0.0.0 --port 8000
