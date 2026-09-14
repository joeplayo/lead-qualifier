import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()

@dataclass(frozen=True)
class Settings:
    app_name: str = os.getenv("APP_NAME", "LeadLift")
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./leadsignal.db")
    groq_api_key: str | None = os.getenv("GROQ_API_KEY")
    groq_model: str = os.getenv("GROQ_MODEL", "openai/gpt-oss-20b")
    admin_api_key: str | None = os.getenv("ADMIN_API_KEY")
    qualification_timeout_seconds: float = float(os.getenv("QUALIFICATION_TIMEOUT_SECONDS", "20"))

    session_cookie_name: str = os.getenv("SESSION_COOKIE_NAME", "leadsignal_session")
    session_ttl_days: int = int(os.getenv("SESSION_TTL_DAYS", "14"))
    session_cookie_secure: bool = os.getenv("SESSION_COOKIE_SECURE", "false").lower() == "true"

    stripe_secret_key: str | None = os.getenv("STRIPE_SECRET_KEY")
    stripe_webhook_secret: str | None = os.getenv("STRIPE_WEBHOOK_SECRET")
    stripe_price_starter: str | None = os.getenv("STRIPE_PRICE_STARTER")
    stripe_price_growth: str | None = os.getenv("STRIPE_PRICE_GROWTH")
    app_base_url: str = os.getenv("APP_BASE_URL", "http://localhost:8000").rstrip("/")
    worker_poll_seconds: float = float(os.getenv("WORKER_POLL_SECONDS", "1"))
    worker_stale_seconds: int = int(os.getenv("WORKER_STALE_SECONDS", "180"))
    qualification_max_attempts: int = int(os.getenv("QUALIFICATION_MAX_ATTEMPTS", "3"))
    notification_timeout_seconds: float = float(os.getenv("NOTIFICATION_TIMEOUT_SECONDS", "10"))

    # Local/dev superuser bootstrap. Disabled automatically for non-SQLite deployments
    # by the bootstrap service unless explicitly managed via the bootstrap script.
    bootstrap_superuser_enabled: bool = os.getenv("BOOTSTRAP_SUPERUSER_ENABLED", "true").lower() == "true"
    bootstrap_superuser_username: str = os.getenv("BOOTSTRAP_SUPERUSER_USERNAME", "admin")
    bootstrap_superuser_password: str = os.getenv("BOOTSTRAP_SUPERUSER_PASSWORD", "joeplayo.com")

settings = Settings()

PLAN_LIMITS = {
    "free": 25,
    "starter": 500,
    "growth": 2500,
}
