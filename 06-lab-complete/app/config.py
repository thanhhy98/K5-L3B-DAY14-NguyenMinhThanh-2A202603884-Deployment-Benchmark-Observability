"""
Config — 12-Factor: mọi cấu hình đọc từ biến môi trường.

Daily budget takes precedence when both budget variables are configured.
"""
import os
from dataclasses import dataclass


@dataclass
class Settings:
    port: int = int(os.getenv("PORT", "8000"))
    environment: str = os.getenv("ENVIRONMENT", "development")
    agent_api_key: str = os.getenv("AGENT_API_KEY", "")
    redis_url: str = os.getenv("REDIS_URL", "")
    rate_limit_per_minute: int = int(os.getenv("RATE_LIMIT_PER_MINUTE", "10"))
    daily_budget_usd: float = float(
        os.getenv("DAILY_BUDGET_USD", os.getenv("MONTHLY_BUDGET_USD", "1.0"))
    )
    budget_period: str = (
        "monthly"
        if "DAILY_BUDGET_USD" not in os.environ
        and "MONTHLY_BUDGET_USD" in os.environ
        else "daily"
    )


settings = Settings()
