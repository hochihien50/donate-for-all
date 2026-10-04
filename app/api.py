import hashlib
import secrets
from functools import wraps

from flask import Blueprint, current_app, g, jsonify, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from sqlalchemy import select
from werkzeug.security import check_password_hash, generate_password_hash

from . import services
from .extensions import db
from .models import ApiKey, Donation, Project, User, utcnow
from .payments import InvalidSignature, ProviderError, ProviderNotEnabled, get_provider

bp = Blueprint("api", __name__)


def err(msg, code):
    return jsonify(error=msg), code


def _ser():
    return URLSafeTimedSerializer(current_app.config["SECRET_KEY"], salt="user-auth")


def require_user(f):
    @wraps(f)
    def w(*a, **k):
        h = request.headers.get("Authorization", "")
        try:
            uid = _ser().loads(h[7:], max_age=7 * 86400)["uid"] if h.startswith("Bearer ") else None
        except BadSignature:
            uid = None
        g.user = db.session.get(User, uid) if uid else None
        return f(*a, **k) if g.user else err("unauthorized", 401)
    return w


def require_api_key(f):
    @wraps(f)
    def w(*a, **k):
        raw = request.headers.get("X-API-Key", "")
        h = hashlib.sha256(raw.encode()).hexdigest()
        key = db.session.execute(
            select(ApiKey).where(ApiKey.key_hash == h, ApiKey.revoked_at.is_(None))
        ).scalar_one_or_none()
        if not raw or not key:
            return err("invalid api key", 401)
        g.project = key.project
        return f(*a, **k)
    return w


def _donation_json(d, order=None):
    order = order or (d.payment_orders[-1] if d.payment_orders else None)
    out = {
        "id": str(d.id), "amount": d.amount, "currency": d.currency, "status": d.status,
        "donor_name": d.donor_name, "message": d.message,
        "created_at": d.created_at.isoformat(),
        "completed_at": d.completed_at.isoformat() if d.completed_at else None,
    }
    if order:
        out["payment"] = {
            "provider": order.provider, "order_id": order.provider_order_id, "status": order.status,
            "payment_url": order.payment_url, "qr_code": order.qr_code, "deeplink": order.deeplink,
        }
    return out


# ---------- auth / projects / api keys ----------
@bp.post("/auth/register")
def register():
    b = request.get_json(silent=True) or {}
    email, pw = str(b.get("email", "")).strip().lower(), str(b.get("password", ""))
    if "@" not in email or len(pw) < 8:
        return err("valid email and password (>= 8 chars) required", 400)
    if db.session.execute(select(User).where(User.email == email)).scalar_one_or_none():
        return err("email already registered", 409)
    u = User(email=email, password_hash=generate_password_hash(pw))
    db.session.add(u)
    db.session.commit()
    return jsonify(id=u.id, email=u.email), 201


@bp.post("/auth/login")
def login():
    b = request.get_json(silent=True) or {}
    u = db.session.execute(select(User).where(User.email == str(b.get("email", "")).lower())).scalar_one_or_none()
    if not u or not check_password_hash(u.password_hash, str(b.get("password", ""))):
        return err("invalid credentials", 401)
    return jsonify(token=_ser().dumps({"uid": u.id}))


@bp.post("/projects")
@require_user
def create_project():
    name = str((request.get_json(silent=True) or {}).get("name", "")).strip()
    if not name:
        return err("name required", 400)
    p = Project(user_id=g.user.id, name=name[:120])
    db.session.add(p)
    db.session.commit()
    return jsonify(id=p.id, name=p.name), 201


@bp.get("/projects")
@require_user
def list_projects():
    rows = db.session.execute(select(Project).where(Project.user_id == g.user.id)).scalars()
    return jsonify([{"id": p.id, "name": p.name} for p in rows])


@bp.post("/projects/<int:pid>/api-keys")
@require_user
def create_api_key(pid):
    p = db.session.get(Project, pid)
    if not p or p.user_id != g.user.id:
        return err("not found", 404)
    raw = "dk_" + secrets.token_urlsafe(32)
    k = ApiKey(project_id=p.id, key_prefix=raw[:8], key_hash=hashlib.sha256(raw.encode()).hexdigest())
    db.session.add(k)
    db.session.commit()
    return jsonify(id=k.id, api_key=raw, note="store it now; it is never shown again"), 201


@bp.delete("/projects/<int:pid>/api-keys/<int:kid>")
@require_user
def revoke_api_key(pid, kid):
    k = db.session.get(ApiKey, kid)
    if not k or k.project_id != pid or k.project.user_id != g.user.id:
        return err("not found", 404)
    k.revoked_at = utcnow()
    db.session.commit()
    return jsonify(revoked=True)


# ---------- donations ----------
@bp.post("/donations/create")
@require_api_key
def create_donation():
    cfg = current_app.config
    b = request.get_json(silent=True) or {}
    if "status" in b:  # clients can never choose the status
        return err("'status' cannot be set by clients", 400)
    amount = b.get("amount")
    if isinstance(amount, bool) or not isinstance(amount, int) or not (
        cfg["MIN_DONATION_VND"] <= amount <= cfg["MAX_DONATION_VND"]
    ):
        return err(f"amount must be an integer VND between {cfg['MIN_DONATION_VND']} and {cfg['MAX_DONATION_VND']}", 400)
    try:
        provider = get_provider(b.get("provider") or cfg["DEFAULT_PROVIDER"], cfg)
    except ProviderNotEnabled:
        return err("payment provider not available", 400)
    try:
        donation, order = services.create_donation(
            provider, g.project.id, amount,
            str(b.get("donor_name", ""))[:120] or None, str(b.get("message", ""))[:500] or None,
        )
    except ProviderError as e:
        current_app.logger.error("provider error: %s", e)
        return err("payment provider error", 502)
    return jsonify(_donation_json(donation, order)), 201


@bp.get("/donations/<uuid:did>")
@require_api_key
def get_donation(did):
    d = db.session.get(Donation, did)
    if not d or d.project_id != g.project.id:
        return err("not found", 404)
    return jsonify(_donation_json(d))


@bp.get("/donations")
@require_api_key
def list_donations():
    limit = min(int(request.args.get("limit", 50)), 200)
    rows = db.session.execute(
        select(Donation).where(Donation.project_id == g.project.id).order_by(Donation.created_at.desc()).limit(limit)
    ).scalars()
    return jsonify([_donation_json(d) for d in rows])


# ---------- webhook (the ONLY path to 'completed') ----------
@bp.post("/webhooks/<provider_name>")
def webhook(provider_name):
    try:
        provider = get_provider(provider_name, current_app.config)
    except ProviderNotEnabled:
        return err("unknown provider", 404)
    try:
        result = provider.parse_webhook(request.headers, request.get_data())
    except InvalidSignature as e:
        current_app.logger.warning("invalid %s webhook: %s", provider_name, e)
        return jsonify(provider.webhook_reject()), 401
    outcome = services.process_webhook(provider_name, result)
    return jsonify(provider.webhook_ack(outcome)), 200
