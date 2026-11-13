# 后端镜像：Python 3.13 对齐本地 venv 版本
FROM python:3.13-slim

WORKDIR /srv

# 先拷依赖清单再装：利用 docker layer 缓存，改业务代码不重装依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY alembic.ini .
COPY alembic ./alembic
COPY app ./app
COPY docker-entrypoint.sh .
RUN chmod +x docker-entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["./docker-entrypoint.sh"]
