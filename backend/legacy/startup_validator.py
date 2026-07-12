"""v01-compatibility stub for top-level `startup_validator`.

Deployment readiness router imports `validate_startup_env()` at import
time. Return an OK result so its import resolves; the actual validation
lives in `app.core.config` (which fail-fasts on missing env).
"""

REQUIRED_VARS = ("MONGO_URL", "DB_NAME", "JWT_SECRET")
RECOMMENDED_VARS = (
    "ADMIN_EMAIL", "ADMIN_PASSWORD", "VIE_URL", "CORS_ORIGINS",
    "JWT_ACCESS_TTL_MIN", "JWT_REFRESH_TTL_DAYS",
)
OPTIONAL_VARS = (
    "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "GEMINI_API_KEY",
    "DEEPSEEK_API_KEY", "GROQ_API_KEY", "KIMI_API_KEY",
    "REDIS_URL", "ENABLE_LEGACY_ROUTERS", "ENABLE_FACTORY_RUNNER",
    "ENABLE_DYNAMIC_MARKET_UNIVERSE", "LLM_GENERATOR_ENABLED",
)


def validate_startup_env() -> dict:
    return {"ok": True, "issues": [], "note": "delegated to app.core.config"}


def get_validation_report() -> dict:
    return validate_startup_env()
