"""
Cost guard (tiêu chí 8).

Spend is shared across workers in Redis and expires at the configured budget boundary.
"""
from datetime import datetime, timedelta, timezone

from fastapi import HTTPException
from redis.exceptions import RedisError

from app.config import settings
from app.redis_client import r

PRICE_INPUT_PER_1K = 0.00015
PRICE_OUTPUT_PER_1K = 0.0006

_RECORD_COST_SCRIPT = """
local total = tonumber(redis.call('GET', KEYS[1]) or '0') + tonumber(ARGV[1])
local formatted = string.format('%.12f', total)
redis.call('SET', KEYS[1], formatted, 'EX', tonumber(ARGV[2]))
return formatted
"""


def _budget_key_and_ttl() -> tuple[str, int]:
    now = datetime.now(timezone.utc)
    if settings.budget_period == "monthly":
        key = f"cost:monthly:{now:%Y-%m}"
        if now.month == 12:
            next_period = now.replace(
                year=now.year + 1, month=1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
        else:
            next_period = now.replace(
                month=now.month + 1, day=1, hour=0, minute=0, second=0, microsecond=0
            )
    else:
        key = f"cost:daily:{now:%Y-%m-%d}"
        next_period = (now + timedelta(days=1)).replace(
            hour=0, minute=0, second=0, microsecond=0
        )
    return key, max(1, int((next_period - now).total_seconds()))


def check_budget() -> None:
    """Gọi TRƯỚC khi gọi LLM. Hết budget → raise HTTPException(status_code=402)."""
    if r is None:
        raise HTTPException(status_code=503, detail="Cost guard requires Redis")
    key, _ = _budget_key_and_ttl()
    try:
        spent = float(r.get(key) or 0)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Cost guard unavailable") from exc
    if spent >= settings.daily_budget_usd:
        raise HTTPException(status_code=402, detail="Daily budget exceeded")


def record_cost(input_tokens: int, output_tokens: int) -> float:
    """Gọi SAU khi gọi LLM. Cộng chi phí của request vào tổng, trả về chi phí request."""
    if r is None:
        raise HTTPException(status_code=503, detail="Cost guard requires Redis")
    if input_tokens < 0 or output_tokens < 0:
        raise ValueError("Token counts must be non-negative")

    cost = (
        input_tokens * PRICE_INPUT_PER_1K + output_tokens * PRICE_OUTPUT_PER_1K
    ) / 1000
    key, ttl = _budget_key_and_ttl()
    try:
        r.eval(_RECORD_COST_SCRIPT, 1, key, f"{cost:.12f}", ttl)
    except RedisError as exc:
        raise HTTPException(status_code=503, detail="Cost guard unavailable") from exc
    return cost
