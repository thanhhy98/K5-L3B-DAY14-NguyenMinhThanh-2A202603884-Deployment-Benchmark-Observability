"""
Rate limiting (tiêu chí 7).

Yêu cầu:
  • Mỗi API key tối đa RATE_LIMIT_PER_MINUTE request trong 60 giây (sliding window)
  • Vượt giới hạn → HTTP 429, nên kèm header Retry-After
  • State lưu trong Redis để mọi worker / instance dùng chung và vẫn còn sau khi
    restart agent (script chấm sẽ restart agent để kiểm tra)
"""
import hashlib
import time
import uuid

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

_RATE_LIMIT_SCRIPT = """
local now = tonumber(ARGV[1])
local window = tonumber(ARGV[2])
local limit = tonumber(ARGV[3])
redis.call('ZREMRANGEBYSCORE', KEYS[1], '-inf', now - window)
local count = redis.call('ZCARD', KEYS[1])
if count >= limit then
    local oldest = redis.call('ZRANGE', KEYS[1], 0, 0, 'WITHSCORES')
    local retry = math.max(1, math.ceil((tonumber(oldest[2]) + window - now) / 1000))
    return {0, retry}
end
redis.call('ZADD', KEYS[1], now, ARGV[4])
redis.call('EXPIRE', KEYS[1], 120)
return {1, 0}
"""


def check_rate_limit(key: str) -> None:
    if r is None:
        raise HTTPException(status_code=503, detail="Rate limiting requires Redis")

    redis_key = f"rate-limit:{hashlib.sha256(key.encode('utf-8')).hexdigest()}"
    now_ms = int(time.time() * 1000)
    try:
        allowed, retry_after = r.eval(
            _RATE_LIMIT_SCRIPT,
            1,
            redis_key,
            now_ms,
            60_000,
            settings.rate_limit_per_minute,
            uuid.uuid4().hex,
        )
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Rate limiter unavailable") from exc

    if not int(allowed):
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded",
            headers={"Retry-After": str(max(1, int(retry_after)))},
        )
