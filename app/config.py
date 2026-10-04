import os


def _csv(name, default=""):
    return [x.strip() for x in os.getenv(name, default).split(",") if x.strip()]


def load_config():
    env = os.getenv("APP_ENV", "development")
    db_url = os.getenv("DATABASE_URL", "")
    if db_url.startswith("postgres://"):  # Render/Heroku legacy scheme
        db_url = "postgresql://" + db_url[len("postgres://"):]
    secret = os.getenv("SECRET_KEY", "")
    providers = _csv("ENABLED_PROVIDERS", "zalopay")
    origins = _csv("ALLOWED_ORIGINS")

    if env == "production":
        problems = []
        if not db_url.startswith("postgresql"):
            problems.append("DATABASE_URL must be a PostgreSQL URL (SQLite is not allowed in production)")
        if len(secret) < 32:
            problems.append("SECRET_KEY must be set (>= 32 chars)")
        if "sandbox" in providers:
            problems.append("the fake 'sandbox' provider cannot be enabled in production")
        if "*" in origins or not origins:
            problems.append("ALLOWED_ORIGINS must list explicit origins")
        if problems:
            raise RuntimeError("Invalid production config: " + "; ".join(problems))
    else:
        db_url = db_url or "postgresql://postgres:postgres@localhost:5432/donate"
        secret = secret or "dev-only-secret-key-change-me-0000000000"
        origins = origins or ["http://localhost:3000"]

    if db_url.startswith("postgresql://"):  # pin the psycopg2 driver explicitly
        db_url = "postgresql+psycopg2://" + db_url[len("postgresql://"):]

    return {
        "APP_ENV": env,
        "SQLALCHEMY_DATABASE_URI": db_url,
        "SQLALCHEMY_ENGINE_OPTIONS": {"pool_pre_ping": True},
        "SECRET_KEY": secret,
        "ALLOWED_ORIGINS": origins,
        "PAYMENT_MODE": os.getenv("PAYMENT_MODE", "sandbox"),
        "ENABLED_PROVIDERS": providers,
        "DEFAULT_PROVIDER": os.getenv("DEFAULT_PROVIDER", "zalopay"),
        "MIN_DONATION_VND": int(os.getenv("MIN_DONATION_VND", "10000")),
        "MAX_DONATION_VND": int(os.getenv("MAX_DONATION_VND", "50000000")),
        "ZALOPAY_APP_ID": os.getenv("ZALOPAY_APP_ID", ""),
        "ZALOPAY_KEY1": os.getenv("ZALOPAY_KEY1", ""),
        "ZALOPAY_KEY2": os.getenv("ZALOPAY_KEY2", ""),
        "ZALOPAY_CALLBACK_URL": os.getenv("ZALOPAY_CALLBACK_URL", ""),
        "ZALOPAY_ENDPOINT": os.getenv("ZALOPAY_ENDPOINT", ""),
        "VIETQR_BANK_ID": os.getenv("VIETQR_BANK_ID", ""),
        "VIETQR_ACCOUNT_NO": os.getenv("VIETQR_ACCOUNT_NO", ""),
        "VIETQR_ACCOUNT_NAME": os.getenv("VIETQR_ACCOUNT_NAME", ""),
        "VIETQR_WEBHOOK_SECRET": os.getenv("VIETQR_WEBHOOK_SECRET", ""),
        "SANDBOX_WEBHOOK_SECRET": os.getenv("SANDBOX_WEBHOOK_SECRET", "sandbox-secret"),
    }
