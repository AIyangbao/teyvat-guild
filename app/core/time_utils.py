from datetime import datetime, timedelta, timezone
def utcnow() -> datetime:
      """统一取 UTC 时间。
      不用 datetime.now()：那是本地时间，服务器换时区后历史数据全部错位。"""
      return datetime.now(timezone.utc).replace(tzinfo=None)

def now_plus(**delta) -> datetime:
      """now_plus(minutes=30)，用来算支付截止时间。"""
      return utcnow() + timedelta(**delta)