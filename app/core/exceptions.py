class BizError(Exception):
    """业务规则违规（库存不足、状态非法、参数越界等）。
    约定：service 层只抛它；router 层统一接住转 4xx 响应。
    区别于 ValueError/KeyError 这些通用异常——它携带的是业务语义。"""
    def __init__(self, message: str, code: str = "BIZ_ERROR"):
        self.code = code
        super().__init__(message)