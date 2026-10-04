from dotenv import load_dotenv
from flask import Flask, jsonify
from flask_cors import CORS

from .config import load_config
from .extensions import db, migrate


def create_app(overrides=None):
    load_dotenv()
    app = Flask(__name__)
    if overrides and overrides.get("APP_ENV") == "testing":
        app.config.update({k: v for k, v in overrides.items()})
        app.config.setdefault("ALLOWED_ORIGINS", ["http://localhost:3000"])
        app.config.setdefault("SECRET_KEY", "test-secret-key-000000000000000000")
        for k, v in {"MIN_DONATION_VND": 10000, "MAX_DONATION_VND": 50000000,
                     "SANDBOX_WEBHOOK_SECRET": "sandbox-secret", "PAYMENT_MODE": "sandbox"}.items():
            app.config.setdefault(k, v)
    else:
        app.config.update(load_config())
        if overrides:
            app.config.update(overrides)

    CORS(app, origins=app.config["ALLOWED_ORIGINS"])
    db.init_app(app)
    migrate.init_app(app, db)  # schema is managed ONLY by migrations (no create_all / drop_all)

    from . import models  # noqa: F401  (register tables for Alembic)
    from .api import bp

    app.register_blueprint(bp, url_prefix="/api/v1")

    @app.get("/health")
    def health():
        return jsonify(status="ok")

    return app
