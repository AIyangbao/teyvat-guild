"""缓存 key 常量：谁导入都不产生循环依赖。"""
HALL_CACHE_PREFIX = "teyvat:hall"      # 大厅列表，分页维度：teyvat:hall:{page}:{page_size}
HALL_CACHE_TTL = 30                    # 秒。兜底寿命：漏失效最多脏 30s