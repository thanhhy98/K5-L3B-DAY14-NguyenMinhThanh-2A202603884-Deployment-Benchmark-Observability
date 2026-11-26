"""
Kết nối Redis dùng chung cho rate limiter và cost guard.

The client is created without connecting so the app can start if Redis is down.
"""
import redis
from redis import Redis
from redis.exceptions import RedisError

from app.config import settings

r: Redis | None = (
    redis.Redis.from_url(
        settings.redis_url,
        decode_responses=True,
        socket_connect_timeout=1,
        socket_timeout=2,
    )
    if settings.redis_url
    else None
)


def redis_healthy() -> bool:
    if r is None:
        return False
    try:
        return bool(r.ping())
    except RedisError:
        return False
