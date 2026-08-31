import base64
import csv
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import RLock
from urllib.parse import quote

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError
from flask import Flask, g, jsonify, make_response, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix


APP_ID = "keyku"
APP_NAME = "Keyku - Key Vault"
APP_SUBTITLE = "Secure Steam key sharing"
APP_VERSION = os.environ.get("APP_VERSION", "0.3.2")
APP_BUILD_DATE = os.environ.get("APP_BUILD_DATE", "local")
APP_GIT_SHA = os.environ.get("GITHUB_SHA", os.environ.get("APP_GIT_SHA", "local"))
PORT = int(os.environ.get("PORT", "3000"))
DATA_DIR = Path(os.environ.get("ISHIKU_DATA_DIR", os.environ.get("DATA_DIR", "/data")))
CSV_PATH = Path(os.environ.get("CSV_PATH", str(DATA_DIR / "keys.csv")))
DATA_DIR = CSV_PATH.parent if "CSV_PATH" in os.environ else DATA_DIR
USERS_PATH = Path(os.environ.get("USERS_PATH", str(DATA_DIR / "users.json")))
REQUESTS_PATH = Path(os.environ.get("REACTIVATION_REQUESTS_PATH", str(DATA_DIR / "reactivation-requests.json")))
PASSWORD_RESET_REQUESTS_PATH = Path(os.environ.get("PASSWORD_RESET_REQUESTS_PATH", str(DATA_DIR / "password-reset-requests.json")))
SESSIONS_PATH = Path(os.environ.get("SESSIONS_PATH", str(DATA_DIR / "sessions.json")))
AUDIT_PATH = Path(os.environ.get("AUDIT_PATH", str(DATA_DIR / "audit.jsonl")))
SECRET_PATH = Path(os.environ.get("SESSION_SECRET_FILE", str(DATA_DIR / "session-secret.txt")))
PUBLIC_DIR = Path(os.environ.get("PUBLIC_DIR", str(Path(__file__).resolve().parent.parent / "public")))
SETUP_STATE_PATH = Path(os.environ.get("SETUP_STATE_PATH", str(DATA_DIR / "setup-state.json")))
SETUP_SECRET_FILE_ENV = "ISHIKU_SETUP_SECRET_FILE"
SETUP_SECRET_ENV = "ISHIKU_SETUP_SECRET"
SETUP_SECRET_FILE_DEFAULT = "/run/secrets/ishiku_setup_secret"
PLACEHOLDER_PASSWORDS = {"admin", "password", "passwort", "changeme", "change-me", "123456", "123456789", "ishiku"}

SESSION_COOKIE = "keyku_session"
SESSION_IDLE_SECONDS = int(os.environ.get("ISHIKU_SESSION_IDLE_SECONDS", str(12 * 60 * 60)))
SESSION_ABSOLUTE_SECONDS = int(os.environ.get("ISHIKU_SESSION_ABSOLUTE_SECONDS", str(14 * 24 * 60 * 60)))
LOGIN_WINDOW_SECONDS = 15 * 60
LOGIN_ACCOUNT_LIMIT = 8
LOGIN_NETWORK_LIMIT = 24
ARGON2 = PasswordHasher(time_cost=2, memory_cost=19456, parallelism=1, hash_len=32, salt_len=16)

app = Flask(__name__, static_folder=None)
app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
if str(os.environ.get("ISHIKU_TRUST_PROXY", "")).lower() in {"1", "true", "yes", "on"}:
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
file_lock = RLock()
setup_attempts = {}
login_attempts = {"account": {}, "network": {}}


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def iso_at(value):
    return value.astimezone(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def parse_iso(value):
    try:
        return datetime.fromisoformat(str(value).replace("Z", "+00:00")).astimezone(timezone.utc)
    except (TypeError, ValueError):
        return datetime.fromtimestamp(0, timezone.utc)


def ensure_dir(path):
    Path(path).mkdir(parents=True, exist_ok=True)


def atomic_write(path, text):
    path = Path(path)
    ensure_dir(path.parent)
    fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as handle:
            handle.write(text)
        os.replace(tmp_name, path)
    finally:
        if os.path.exists(tmp_name):
            os.unlink(tmp_name)


def read_json(path, fallback):
    path = Path(path)
    if not path.exists():
        return fallback
    raw = path.read_text(encoding="utf-8")
    if not raw.strip():
        return fallback
    return json.loads(raw)


def write_json(path, data):
    atomic_write(path, json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def get_session_secret():
    env_secret = os.environ.get("SESSION_SECRET", "")
    if len(env_secret) >= 32:
        return env_secret
    ensure_dir(DATA_DIR)
    if SECRET_PATH.exists():
        existing = SECRET_PATH.read_text(encoding="utf-8").strip()
        if len(existing) >= 32:
            return existing
    generated = secrets.token_urlsafe(48)
    atomic_write(SECRET_PATH, generated + "\n")
    return generated


SESSION_SECRET = get_session_secret()


def b64url(data):
    return base64.urlsafe_b64encode(data).decode("ascii").rstrip("=")


def safe_equal(left, right):
    return hmac.compare_digest(str(left), str(right))


def public_user(user):
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "displayName": user.get("displayName") or user.get("username"),
        "email": user.get("email") or "",
        "role": user.get("role"),
        "status": user.get("status"),
        "createdAt": user.get("createdAt"),
        "approvedAt": user.get("approvedAt"),
    }


def normalize_username(username):
    return str(username or "").strip().lower()


def validate_password(password, min_length=10):
    clean = str(password or "")
    if len(clean) < min_length or len(clean) > 200:
        return f"Password must be {min_length} to 200 characters."
    return None


def validate_credentials(username, password, min_password_length=10):
    clean_username = normalize_username(username)
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789._-"
    if len(clean_username) < 3 or len(clean_username) > 32 or any(ch not in allowed for ch in clean_username):
        return "Username must be 3-32 characters and may contain a-z, 0-9, dot, underscore, and hyphen."
    return validate_password(password, min_password_length)


def validate_username(username):
    return validate_credentials(username, "temporary-valid-password", min_password_length=12)


def hash_password(password):
    return {"algorithm": "argon2id", "hash": ARGON2.hash(str(password))}


def verify_password(password, user):
    if not user:
        return False
    expected = user.get("passwordHash", "")
    if user.get("passwordAlgorithm") == "argon2id" or str(expected).startswith("$argon2id$"):
        try:
            return ARGON2.verify(expected, str(password))
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    salt = str(user.get("salt") or "")
    iterations = int(user.get("iterations") or 310000)
    if not salt or not expected:
        return False
    digest = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt.encode("utf-8"), iterations, dklen=32)
    return safe_equal(b64url(digest), expected)


def password_needs_upgrade(user):
    encoded = str(user.get("passwordHash") or "")
    if user.get("passwordAlgorithm") != "argon2id" or not encoded.startswith("$argon2id$"):
        return True
    try:
        return ARGON2.check_needs_rehash(encoded)
    except InvalidHashError:
        return True


def read_users():
    data = read_json(USERS_PATH, {"users": []})
    return data if isinstance(data.get("users"), list) else {"users": []}


def write_users(data):
    write_json(USERS_PATH, data)


def read_sessions():
    data = read_json(SESSIONS_PATH, {"sessions": []})
    return data if isinstance(data.get("sessions"), list) else {"sessions": []}


def write_sessions(data):
    write_json(SESSIONS_PATH, data)


def audit_event(event, *, actor=None, target=None, result="success"):
    entry = {
        "time": now_iso(),
        "requestId": getattr(g, "request_id", None),
        "event": event,
        "actor": actor,
        "target": target,
        "result": result,
    }
    ensure_dir(AUDIT_PATH.parent)
    with file_lock:
        with AUDIT_PATH.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":"), ensure_ascii=False) + "\n")
        AUDIT_PATH.chmod(0o600)


def read_reactivation_requests():
    data = read_json(REQUESTS_PATH, {"requests": []})
    return data if isinstance(data.get("requests"), list) else {"requests": []}


def write_reactivation_requests(data):
    write_json(REQUESTS_PATH, data)


def read_password_reset_requests():
    data = read_json(PASSWORD_RESET_REQUESTS_PATH, {"requests": []})
    return data if isinstance(data.get("requests"), list) else {"requests": []}


def write_password_reset_requests(data):
    write_json(PASSWORD_RESET_REQUESTS_PATH, data)


def read_setup_state():
    data = read_json(SETUP_STATE_PATH, {"setupCompleted": False})
    return data if isinstance(data, dict) else {"setupCompleted": False}


def write_setup_state(data):
    write_json(SETUP_STATE_PATH, data)


def admin_exists(users=None):
    users = users if users is not None else read_users()["users"]
    return any(user.get("role") == "admin" and user.get("status") == "approved" for user in users)


def setup_completed():
    users = read_users()["users"]
    state = read_setup_state()
    completed = bool(state.get("setupCompleted")) and admin_exists(users)
    if admin_exists(users) and not state.get("setupCompleted"):
        write_setup_state({"setupCompleted": True, "completedAt": now_iso(), "migrated": True})
        completed = True
    return completed


def read_setup_secret():
    configured_file = os.environ.get(SETUP_SECRET_FILE_ENV)
    file_path = Path(configured_file or SETUP_SECRET_FILE_DEFAULT)
    file_was_explicit = bool(configured_file)

    if file_path.exists():
        try:
            secret = file_path.read_text(encoding="utf-8").strip()
        except OSError:
            return {"ok": False, "secret": "", "errorKey": SETUP_SECRET_FILE_ENV, "message": f"{SETUP_SECRET_FILE_ENV} is unreadable."}
        if len(secret) >= 32:
            return {"ok": True, "secret": secret, "source": "file"}
        if secret:
            return {"ok": False, "secret": "", "errorKey": SETUP_SECRET_FILE_ENV, "message": f"{SETUP_SECRET_FILE_ENV} must contain at least 32 characters."}
        return {"ok": False, "secret": "", "errorKey": SETUP_SECRET_FILE_ENV, "message": f"{SETUP_SECRET_FILE_ENV} is empty."}

    if file_was_explicit:
        return {"ok": False, "secret": "", "errorKey": SETUP_SECRET_FILE_ENV, "message": f"{SETUP_SECRET_FILE_ENV} is configured but missing."}

    env_secret = os.environ.get(SETUP_SECRET_ENV, "").strip()
    if len(env_secret) >= 32:
        return {"ok": True, "secret": env_secret, "source": "env"}
    if env_secret:
        return {"ok": False, "secret": "", "errorKey": SETUP_SECRET_ENV, "message": f"{SETUP_SECRET_ENV} must contain at least 32 characters."}

    return {"ok": False, "secret": "", "errorKey": SETUP_SECRET_ENV, "message": f"{SETUP_SECRET_ENV} or {SETUP_SECRET_FILE_ENV} is required."}


def setup_status_payload():
    completed = setup_completed()
    if completed:
        return {"setupRequired": False, "setupCompleted": True, "setupConfigured": True}
    secret = read_setup_secret()
    return {
        "setupRequired": True,
        "setupCompleted": False,
        "setupConfigured": bool(secret.get("ok")),
        "errorKey": None if secret.get("ok") else secret.get("errorKey"),
        "message": None if secret.get("ok") else secret.get("message"),
    }


def setup_rate_limited(remote_addr):
    now = datetime.now().timestamp()
    key = remote_addr or "unknown"
    attempts = [stamp for stamp in setup_attempts.get(key, []) if now - stamp < 15 * 60]
    setup_attempts[key] = attempts
    return len(attempts) >= 8


def record_failed_setup_attempt(remote_addr):
    key = remote_addr or "unknown"
    setup_attempts.setdefault(key, []).append(datetime.now().timestamp())


def login_signal(scope, username=""):
    remote = request.remote_addr or "unknown"
    if scope == "account":
        value = normalize_username(username) or "unknown"
    else:
        value = remote
    return hmac.new(SESSION_SECRET.encode("utf-8"), f"login:{scope}:{value}".encode("utf-8"), hashlib.sha256).hexdigest()


def login_rate_limited(username):
    now = datetime.now().timestamp()
    signals = (("account", login_signal("account", username), LOGIN_ACCOUNT_LIMIT), ("network", login_signal("network"), LOGIN_NETWORK_LIMIT))
    limited = False
    for scope, key, limit in signals:
        recent = [stamp for stamp in login_attempts[scope].get(key, []) if now - stamp < LOGIN_WINDOW_SECONDS]
        login_attempts[scope][key] = recent
        limited = limited or len(recent) >= limit
    return limited


def record_login_attempt(username, success):
    account_key = login_signal("account", username)
    network_key = login_signal("network")
    if success:
        login_attempts["account"].pop(account_key, None)
        return
    stamp = datetime.now().timestamp()
    login_attempts["account"].setdefault(account_key, []).append(stamp)
    login_attempts["network"].setdefault(network_key, []).append(stamp)


def validate_setup_admin(data, configured_secret):
    username = normalize_username(data.get("adminUsername") or data.get("username"))
    display_name = str(data.get("displayName") or data.get("adminDisplayName") or "").strip()
    email = str(data.get("email") or "").strip()
    password = str(data.get("password") or "")
    confirm = str(data.get("passwordConfirm") or "")
    secret = str(data.get("setupSecret") or "")

    credential_error = validate_credentials(username, password, min_password_length=12)
    if credential_error:
        return credential_error
    if not display_name or len(display_name) > 80:
        return "Display name is required and must be at most 80 characters."
    if len(email) > 180:
        return "Email address is too long."
    if password != confirm:
        return "Password confirmation does not match."
    if not secret.strip() or not safe_equal(secret, configured_secret):
        return "Setup secret is incorrect."
    if safe_equal(password, configured_secret):
        return "Admin password must not match the setup secret."
    normalized_password = password.strip().lower()
    if normalized_password in PLACEHOLDER_PASSWORDS:
        return "Please choose a stronger admin password."
    if normalized_password in {username, APP_ID, APP_NAME.lower()}:
        return "Admin password must not match the username or app name."
    return None


def cookie_secure():
    configured = str(os.environ.get("ISHIKU_COOKIE_SECURE", "auto")).strip().lower()
    if configured in {"1", "true", "yes", "on"}:
        return True
    if configured in {"0", "false", "no", "off"}:
        return False
    public_url = str(os.environ.get("ISHIKU_APP_URL") or "").strip().lower()
    return public_url.startswith("https://") or request.is_secure


def session_token_hash(token):
    return hmac_token("session:v1", token)


def csrf_token_hash(token):
    return hmac_token("csrf:v1", token)


def prune_sessions(data):
    current = datetime.now(timezone.utc)
    sessions = []
    for session in data.get("sessions", []):
        if parse_iso(session.get("idleExpiresAt")) <= current:
            continue
        if parse_iso(session.get("absoluteExpiresAt")) <= current:
            continue
        sessions.append(session)
    changed = len(sessions) != len(data.get("sessions", []))
    data["sessions"] = sessions
    return changed


def create_session(user):
    token = secrets.token_urlsafe(48)
    csrf_token = secrets.token_urlsafe(32)
    created = datetime.now(timezone.utc)
    session = {
        "id": secrets.token_urlsafe(18),
        "tokenHash": session_token_hash(token),
        "csrfHash": csrf_token_hash(csrf_token),
        "csrfToken": csrf_token,
        "userId": user["id"],
        "createdAt": iso_at(created),
        "lastSeenAt": iso_at(created),
        "idleExpiresAt": iso_at(created + timedelta(seconds=SESSION_IDLE_SECONDS)),
        "absoluteExpiresAt": iso_at(created + timedelta(seconds=SESSION_ABSOLUTE_SECONDS)),
        "userAgent": str(request.headers.get("User-Agent") or "Unknown device")[:180],
    }
    with file_lock:
        data = read_sessions()
        prune_sessions(data)
        data["sessions"].append(session)
        write_sessions(data)
    return token, csrf_token, session


def session_context(update_activity=True):
    if hasattr(g, "keyku_session_context"):
        return g.keyku_session_context
    token = request.cookies.get(SESSION_COOKIE)
    if not token:
        g.keyku_session_context = (None, None)
        return g.keyku_session_context
    token_hash = session_token_hash(token)
    with file_lock:
        data = read_sessions()
        changed = prune_sessions(data)
        session = next((item for item in data["sessions"] if safe_equal(item.get("tokenHash", ""), token_hash)), None)
        if session:
            user = next((candidate for candidate in read_users()["users"] if candidate.get("id") == session.get("userId")), None)
            if not user or user.get("status") != "approved":
                data["sessions"] = [item for item in data["sessions"] if item.get("id") != session.get("id")]
                session = None
                changed = True
            elif update_activity:
                current = datetime.now(timezone.utc)
                last_seen = parse_iso(session.get("lastSeenAt"))
                if current - last_seen >= timedelta(minutes=1):
                    session["lastSeenAt"] = iso_at(current)
                    session["idleExpiresAt"] = iso_at(current + timedelta(seconds=SESSION_IDLE_SECONDS))
                    changed = True
        else:
            user = None
        if changed:
            write_sessions(data)
    g.keyku_session_context = (user if session else None, session)
    return g.keyku_session_context


def revoke_sessions(user_id, *, keep_session_id=None):
    with file_lock:
        data = read_sessions()
        before = len(data["sessions"])
        data["sessions"] = [
            item for item in data["sessions"]
            if item.get("userId") != user_id or item.get("id") == keep_session_id
        ]
        removed = before - len(data["sessions"])
        if removed:
            write_sessions(data)
    return removed


def revoke_session(session_id, user_id=None):
    with file_lock:
        data = read_sessions()
        before = len(data["sessions"])
        data["sessions"] = [
            item for item in data["sessions"]
            if item.get("id") != session_id or (user_id is not None and item.get("userId") != user_id)
        ]
        removed = before - len(data["sessions"])
        if removed:
            write_sessions(data)
    return removed


def set_session_cookie(response, user):
    token, csrf_token, _session = create_session(user)
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_ABSOLUTE_SECONDS,
        httponly=True,
        secure=cookie_secure(),
        samesite="Lax",
        path="/",
    )
    response.headers["X-CSRF-Token"] = csrf_token
    return response


def clear_session_cookie(response):
    response.set_cookie(SESSION_COOKIE, "", max_age=0, httponly=True, secure=cookie_secure(), samesite="Lax", path="/")
    return response


def current_user():
    user, _session = session_context()
    return user


def require_auth():
    user = current_user()
    if not user:
        return None, (jsonify({"error": "Login required"}), 401)
    return user, None


def require_admin():
    user, error = require_auth()
    if error:
        return None, error
    if user.get("role") != "admin":
        return None, (jsonify({"error": "Admin privileges required"}), 403)
    return user, None


def ensure_csv():
    ensure_dir(DATA_DIR)
    if not CSV_PATH.exists():
        CSV_PATH.write_text("Game,Key,RedeemedAt,addedAt,RedeemedBy,RedeemedByName\n", encoding="utf-8")


def detect_delimiter(raw):
    first_line = raw.splitlines()[0] if raw.splitlines() else ""
    return ";" if first_line.count(";") > first_line.count(",") else ","


def read_keys():
    ensure_csv()
    raw = CSV_PATH.read_text(encoding="utf-8-sig")
    if not raw.strip():
        return []
    delimiter = detect_delimiter(raw)
    rows = csv.DictReader(raw.splitlines(), delimiter=delimiter)
    keys = []
    for record in rows:
        keys.append({
            "game": str(record.get("Game") or record.get("game") or record.get("Name") or record.get("name") or "").strip(),
            "key": str(record.get("Key") or record.get("key") or "").strip(),
            "redeemedAt": str(record.get("RedeemedAt") or record.get("redeemedAt") or record.get("redeemed_at") or record.get("Redeemed") or record.get("redeemed") or "").strip(),
            "addedAt": str(record.get("addedAt") or record.get("AddedAt") or record.get("added_at") or record.get("Added") or record.get("added") or "").strip(),
            "redeemedBy": str(record.get("RedeemedBy") or record.get("redeemedBy") or record.get("redeemed_by") or "").strip(),
            "redeemedByName": str(record.get("RedeemedByName") or record.get("redeemedByName") or record.get("redeemed_by_name") or record.get("RedeemedUser") or record.get("redeemedUser") or "").strip(),
        })
    return keys


def write_keys(keys):
    ensure_csv()
    delimiter = ","
    if CSV_PATH.exists():
        delimiter = detect_delimiter(CSV_PATH.read_text(encoding="utf-8-sig"))
    output = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8", newline="")
    writer = csv.DictWriter(output, fieldnames=["game", "key", "redeemedAt", "addedAt", "redeemedBy", "redeemedByName"], delimiter=delimiter)
    output.write(delimiter.join(["Game", "Key", "RedeemedAt", "addedAt", "RedeemedBy", "RedeemedByName"]) + "\n")
    for entry in keys:
        writer.writerow({
            "game": entry.get("game", ""),
            "key": entry.get("key", ""),
            "redeemedAt": entry.get("redeemedAt", ""),
            "addedAt": entry.get("addedAt", ""),
            "redeemedBy": entry.get("redeemedBy", "") if entry.get("redeemedAt") else "",
            "redeemedByName": entry.get("redeemedByName", "") if entry.get("redeemedAt") else "",
        })
    output.seek(0)
    atomic_write(CSV_PATH, output.read())
    output.close()


def clean_key_entry(data, existing=None):
    existing = existing or {}
    redeemed_at = str(data.get("redeemedAt", existing.get("redeemedAt", "")) or "").strip()
    return {
        "game": str(data.get("game", existing.get("game", "")) or "").strip(),
        "key": str(data.get("key", existing.get("key", "")) or "").strip(),
        "redeemedAt": redeemed_at,
        "addedAt": str(data.get("addedAt", existing.get("addedAt", "")) or "").strip(),
        "redeemedBy": str(existing.get("redeemedBy", "") or "").strip() if redeemed_at else "",
        "redeemedByName": str(existing.get("redeemedByName", "") or "").strip() if redeemed_at else "",
    }


def validate_key_entry(entry):
    if not entry.get("game"):
        return "Game name is required."
    if not entry.get("key"):
        return "Steam key is required."
    if len(entry["game"]) > 180:
        return "Game name is too long."
    if len(entry["key"]) > 140:
        return "Steam key is too long."
    return None


def steam_redeem_url(key):
    return f"https://store.steampowered.com/account/registerkey?key={quote(str(key or ''))}"


def steam_search_url(game):
    return f"https://store.steampowered.com/search/?term={quote(str(game or ''))}"


def steamdb_url(game):
    return f"https://steamdb.info/search/?a=app&q={quote(str(game or ''))}"


def hmac_token(prefix, value):
    return b64url(hmac.new(SESSION_SECRET.encode("utf-8"), f"{prefix}:{value}".encode("utf-8"), hashlib.sha256).digest())


def share_token_for_key(key):
    return hmac_token("share-key:v1", key)


def key_fingerprint(key):
    return hmac_token("key-fingerprint:v1", key)


def public_base_url():
    configured = (os.environ.get("ISHIKU_APP_URL") or os.environ.get("PUBLIC_BASE_URL") or os.environ.get("APP_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    proto = request.headers.get("X-Forwarded-Proto") or request.scheme
    host = request.headers.get("X-Forwarded-Host") or request.host
    return f"{proto.split(',')[0].strip()}://{host}"


def public_key(entry, index, include_audit=False):
    item = {
        "index": index,
        "game": entry.get("game", ""),
        "redeemed": bool(entry.get("redeemedAt")),
        "redeemedAt": entry.get("redeemedAt") or None,
        "addedAt": entry.get("addedAt") or None,
    }
    if include_audit:
        item["redeemedBy"] = entry.get("redeemedBy") or None
        item["redeemedByName"] = entry.get("redeemedByName") or None
    return item


def public_reactivation_request(req):
    return {
        "id": req.get("id"),
        "index": req.get("index"),
        "game": req.get("game"),
        "status": req.get("status"),
        "requestedBy": req.get("requestedBy"),
        "requestedByName": req.get("requestedByName"),
        "createdAt": req.get("createdAt"),
        "resolvedAt": req.get("resolvedAt"),
        "resolvedBy": req.get("resolvedBy"),
    }


def public_password_reset_request(req):
    return {
        "id": req.get("id"),
        "userId": req.get("userId"),
        "username": req.get("username"),
        "status": req.get("status"),
        "createdAt": req.get("createdAt"),
        "resolvedAt": req.get("resolvedAt"),
        "resolvedBy": req.get("resolvedBy"),
    }


def find_key_by_request(keys, req):
    index = req.get("index")
    fingerprint = req.get("keyFingerprint", "")
    if isinstance(index, int) and 0 <= index < len(keys) and safe_equal(key_fingerprint(keys[index].get("key", "")), fingerprint):
        return index, keys[index]
    for idx, entry in enumerate(keys):
        if safe_equal(key_fingerprint(entry.get("key", "")), fingerprint):
            return idx, entry
    return None, None


def json_body():
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


PUBLIC_MUTATION_PATHS = {
    "/api/setup/register-admin",
    "/api/auth/register",
    "/api/auth/login",
    "/api/auth/password-reset-request",
}


@app.before_request
def request_security():
    g.request_id = secrets.token_hex(12)
    if request.method in {"GET", "HEAD", "OPTIONS"} or not request.path.startswith("/api/"):
        return None
    fetch_site = str(request.headers.get("Sec-Fetch-Site") or "").lower()
    if fetch_site == "cross-site":
        return jsonify({"error": "Cross-site request rejected."}), 403
    origin = request.headers.get("Origin")
    if origin and origin != request.host_url.rstrip("/"):
        return jsonify({"error": "Request origin rejected."}), 403
    if request.path in PUBLIC_MUTATION_PATHS:
        return None
    user, session = session_context(update_activity=False)
    if not user or not session:
        return None
    supplied = str(request.headers.get("X-CSRF-Token") or "")
    if not supplied or not safe_equal(csrf_token_hash(supplied), session.get("csrfHash", "")):
        audit_event("csrf.validation", actor=user.get("id"), result="denied")
        return jsonify({"error": "Request verification failed. Refresh the page and try again."}), 403
    return None


@app.errorhandler(413)
def request_too_large(_error):
    return jsonify({"error": "Request body is too large."}), 413


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Content-Security-Policy"] = "default-src 'self'; img-src 'self' data:; style-src 'self'; script-src 'self'; connect-src 'self'; object-src 'none'; base-uri 'self'; frame-ancestors 'none'"
    response.headers["Cross-Origin-Opener-Policy"] = "same-origin"
    response.headers["Cross-Origin-Resource-Policy"] = "same-origin"
    response.headers["X-Request-ID"] = getattr(g, "request_id", "")
    if request.is_secure:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    if request.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
        payload = response.get_json(silent=True) if response.is_json else None
        if response.status_code >= 400 and isinstance(payload, dict) and isinstance(payload.get("error"), str):
            error_codes = {
                400: "invalid_request",
                401: "authentication_required",
                403: "forbidden",
                404: "not_found",
                409: "conflict",
                413: "payload_too_large",
                422: "validation_failed",
                429: "rate_limited",
                503: "service_unavailable",
            }
            payload.setdefault("code", error_codes.get(response.status_code, "request_failed"))
            payload.setdefault("message", payload["error"])
            payload.setdefault("requestId", getattr(g, "request_id", ""))
            response.set_data(json.dumps(payload, ensure_ascii=False, separators=(",", ":")))
    return response


@app.get("/healthz")
def healthz():
    return jsonify({"ok": True, "app": APP_ID})


@app.get("/readyz")
def readyz():
    payload = {"ok": True, "app": APP_ID, "dataWritable": True, "setup": setup_status_payload()}
    try:
        ensure_dir(DATA_DIR)
        test_path = DATA_DIR / ".readyz"
        test_path.write_text(now_iso(), encoding="utf-8")
        test_path.unlink(missing_ok=True)
    except Exception:
        payload["ok"] = False
        payload["dataWritable"] = False
        return jsonify(payload), 503
    if payload["setup"].get("setupRequired") and not payload["setup"].get("setupConfigured"):
        payload["ok"] = False
        return jsonify(payload), 503
    return jsonify(payload)


@app.get("/api/setup/status")
def api_setup_status():
    return jsonify(setup_status_payload())


@app.get("/api/app/about")
def api_app_about():
    return jsonify({
        "app": {
            "id": APP_ID,
            "name": APP_NAME,
            "subtitle": APP_SUBTITLE,
            "version": APP_VERSION,
            "buildDate": APP_BUILD_DATE,
            "gitSha": APP_GIT_SHA,
        }
    })


@app.post("/api/setup/register-admin")
def api_setup_register_admin():
    if setup_completed():
        return jsonify({"error": "Setup is already complete."}), 409
    if setup_rate_limited(request.remote_addr):
        return jsonify({"error": "Too many setup attempts. Please wait before trying again."}), 429

    secret_state = read_setup_secret()
    if not secret_state.get("ok"):
        return jsonify({"error": secret_state.get("message") or "Setup secret is not configured.", "errorKey": secret_state.get("errorKey")}), 503

    body = json_body()
    error = validate_setup_admin(body, secret_state["secret"])
    if error:
        record_failed_setup_attempt(request.remote_addr)
        return jsonify({"error": error}), 400

    username = normalize_username(body.get("adminUsername") or body.get("username"))
    with file_lock:
        data = read_users()
        if admin_exists(data["users"]):
            return jsonify({"error": "Setup is already complete."}), 409
        if any(user.get("username") == username for user in data["users"]):
            return jsonify({"error": "This username is already taken."}), 409
        hashed = hash_password(body.get("password"))
        created = now_iso()
        user = {
            "id": secrets.token_urlsafe(24),
            "username": username,
            "displayName": str(body.get("displayName") or body.get("adminDisplayName") or username).strip(),
            "email": str(body.get("email") or "").strip(),
            "passwordHash": hashed["hash"],
            "passwordAlgorithm": hashed["algorithm"],
            "role": "admin",
            "status": "approved",
            "createdAt": created,
            "approvedAt": created,
            "approvedBy": "setup",
        }
        data["users"].append(user)
        write_users(data)
        write_setup_state({"setupCompleted": True, "completedAt": created})

    audit_event("setup.admin_created", actor=user["id"], target=user["id"])
    response = make_response(jsonify({"ok": True, "user": public_user(user), "setupCompleted": True}), 201)
    return set_session_cookie(response, user)


@app.get("/api/auth/me")
def auth_me():
    setup_state = setup_status_payload()
    if setup_state.get("setupRequired"):
        return jsonify({"authenticated": False, **setup_state})
    user, session = session_context()
    if not user:
        return jsonify({"authenticated": False, **setup_state})
    users = read_users()["users"]
    pending_users = sum(1 for candidate in users if candidate.get("status") == "pending")
    pending_reactivations = sum(1 for req in read_reactivation_requests()["requests"] if req.get("status") == "pending")
    pending_resets = sum(1 for req in read_password_reset_requests()["requests"] if req.get("status") == "pending")
    count = pending_users + pending_reactivations + pending_resets if user.get("role") == "admin" else 0
    response = make_response(jsonify({"authenticated": True, "user": public_user(user), "pendingCount": pending_users if user.get("role") == "admin" else 0, "notificationCount": count}))
    response.headers["X-CSRF-Token"] = session.get("csrfToken", "")
    return response


@app.post("/api/auth/register")
def auth_register():
    if not setup_completed():
        return jsonify({"error": "Setup must be completed before account requests can be sent."}), 409
    body = json_body()
    username = normalize_username(body.get("username"))
    password = str(body.get("password") or "")
    credential_error = validate_credentials(username, password, min_password_length=12)
    if credential_error:
        return jsonify({"error": credential_error}), 400
    display_name = str(body.get("displayName") or username).strip()
    email = str(body.get("email") or "").strip()
    if not display_name or len(display_name) > 80:
        return jsonify({"error": "Display name is required and must be at most 80 characters."}), 400
    if len(email) > 180:
        return jsonify({"error": "Email address is too long."}), 400
    if password.strip().lower() in PLACEHOLDER_PASSWORDS or password.strip().lower() in {username, APP_ID, APP_NAME.lower()}:
        return jsonify({"error": "Please choose a stronger password."}), 400
    with file_lock:
        data = read_users()
        if any(user.get("username") == username for user in data["users"]):
            return jsonify({"error": "This username is already taken."}), 409
        hashed = hash_password(password)
        user = {
            "id": secrets.token_urlsafe(24),
            "username": username,
            "displayName": display_name,
            "email": email,
            "passwordHash": hashed["hash"],
            "passwordAlgorithm": hashed["algorithm"],
            "role": "user",
            "status": "pending",
            "createdAt": now_iso(),
        }
        data["users"].append(user)
        write_users(data)
    return jsonify({"ok": True, "message": "Account request sent. An admin must approve it before you can sign in.", "user": public_user(user)}), 202


@app.post("/api/auth/login")
def auth_login():
    body = json_body()
    username = normalize_username(body.get("username"))
    password = str(body.get("password") or "")
    if login_rate_limited(username):
        audit_event("auth.sign_in", target=username or None, result="rate_limited")
        return jsonify({"error": "Sign-in temporarily unavailable. Try again later."}), 429
    user = next((candidate for candidate in read_users()["users"] if candidate.get("username") == username), None)
    valid = bool(user and verify_password(password, user) and user.get("status") == "approved")
    record_login_attempt(username, valid)
    if not valid:
        audit_event("auth.sign_in", target=username or None, result="denied")
        return jsonify({"error": "Username or password is incorrect."}), 401
    if password_needs_upgrade(user):
        with file_lock:
            data = read_users()
            stored = next((candidate for candidate in data["users"] if candidate.get("id") == user.get("id")), None)
            if stored and verify_password(password, stored):
                set_user_password(stored, password, stored["id"])
                write_users(data)
                user = stored
                audit_event("auth.password_hash_upgraded", actor=user["id"], target=user["id"])
    _previous_user, previous_session = session_context(update_activity=False)
    if previous_session:
        revoke_session(previous_session.get("id"), user["id"])
    audit_event("auth.sign_in", actor=user["id"], target=user["id"])
    response = make_response(jsonify({"ok": True, "user": public_user(user)}))
    return set_session_cookie(response, user)


@app.post("/api/auth/password-reset-request")
def password_reset_request():
    username = normalize_username(json_body().get("username"))
    user = next((candidate for candidate in read_users()["users"] if candidate.get("username") == username), None)
    if user and user.get("status") != "rejected":
        with file_lock:
            data = read_password_reset_requests()
            exists = any(req.get("status") == "pending" and req.get("userId") == user.get("id") for req in data["requests"])
            if not exists:
                data["requests"].append({"id": secrets.token_urlsafe(24), "userId": user["id"], "username": user["username"], "status": "pending", "createdAt": now_iso()})
                write_password_reset_requests(data)
    return jsonify({"ok": True, "message": "If the user exists, a password reset request was sent to the admin."})


@app.post("/api/auth/logout")
def auth_logout():
    user, session = session_context(update_activity=False)
    if user and session:
        revoke_session(session.get("id"), user["id"])
        audit_event("auth.sign_out", actor=user["id"], target=session.get("id"))
    response = make_response(jsonify({"ok": True}))
    return clear_session_cookie(response)


@app.get("/api/auth/sessions")
def auth_sessions():
    user, error = require_auth()
    if error:
        return error
    _active_user, active = session_context()
    with file_lock:
        data = read_sessions()
        changed = prune_sessions(data)
        sessions = [item for item in data["sessions"] if item.get("userId") == user.get("id")]
        if changed:
            write_sessions(data)
    return jsonify({
        "sessions": [
            {
                "id": item.get("id"),
                "createdAt": item.get("createdAt"),
                "lastSeenAt": item.get("lastSeenAt"),
                "absoluteExpiresAt": item.get("absoluteExpiresAt"),
                "userAgent": item.get("userAgent"),
                "current": item.get("id") == active.get("id"),
            }
            for item in sorted(sessions, key=lambda value: str(value.get("lastSeenAt")), reverse=True)
        ]
    })


@app.delete("/api/auth/sessions/<session_id>")
def auth_session_revoke(session_id):
    user, error = require_auth()
    if error:
        return error
    _active_user, active = session_context(update_activity=False)
    with file_lock:
        data = read_sessions()
        target = next((item for item in data["sessions"] if item.get("id") == session_id and item.get("userId") == user.get("id")), None)
        if not target:
            return jsonify({"error": "Session not found"}), 404
        data["sessions"] = [item for item in data["sessions"] if item.get("id") != session_id]
        write_sessions(data)
    audit_event("auth.session_revoked", actor=user["id"], target=session_id)
    response = make_response(jsonify({"ok": True, "current": session_id == active.get("id")}))
    return clear_session_cookie(response) if session_id == active.get("id") else response


@app.patch("/api/account")
def account_update():
    current, error = require_auth()
    if error:
        return error
    body = json_body()
    username = normalize_username(body.get("username") or current.get("username"))
    display_name = str(body.get("displayName") or "").strip()
    email = str(body.get("email") or "").strip()
    new_password = str(body.get("newPassword") or "")
    password_confirm = str(body.get("passwordConfirm") or "")
    current_password = str(body.get("currentPassword") or "")

    credential_error = validate_username(username)
    if credential_error:
        return jsonify({"error": credential_error}), 400
    if not display_name or len(display_name) > 80:
        return jsonify({"error": "Display name is required and must be at most 80 characters."}), 400
    if len(email) > 180:
        return jsonify({"error": "Email address is too long."}), 400
    if new_password:
        password_error = validate_credentials(username, new_password, min_password_length=12)
        if password_error:
            return jsonify({"error": password_error}), 400
        if new_password != password_confirm:
            return jsonify({"error": "Password confirmation does not match."}), 400
        normalized_password = new_password.strip().lower()
        if normalized_password in PLACEHOLDER_PASSWORDS or normalized_password in {username, APP_ID, APP_NAME.lower()}:
            return jsonify({"error": "Please choose a stronger password."}), 400
        if not verify_password(current_password, current):
            return jsonify({"error": "Current password is incorrect."}), 403

    with file_lock:
        data = read_users()
        user = next((candidate for candidate in data["users"] if candidate.get("id") == current.get("id")), None)
        if not user:
            return jsonify({"error": "User not found"}), 404
        if any(candidate.get("id") != user.get("id") and candidate.get("username") == username for candidate in data["users"]):
            return jsonify({"error": "This username is already taken."}), 409
        user["username"] = username
        user["displayName"] = display_name
        user["email"] = email
        if new_password:
            set_user_password(user, new_password, user["id"])
        write_users(data)
    if new_password:
        revoke_sessions(user["id"])
        audit_event("auth.password_changed", actor=user["id"], target=user["id"])
        response = make_response(jsonify({"ok": True, "user": public_user(user), "sessionRotated": True}))
        return set_session_cookie(response, user)
    return jsonify({"ok": True, "user": public_user(user)})


@app.get("/api/admin/notifications")
def admin_notifications():
    admin, error = require_admin()
    if error:
        return error
    users = read_users()["users"]
    pending_users = sorted([public_user(user) for user in users if user.get("status") == "pending"], key=lambda item: str(item.get("createdAt")))
    reactivations = sorted([public_reactivation_request(req) for req in read_reactivation_requests()["requests"] if req.get("status") == "pending"], key=lambda item: str(item.get("createdAt")))
    resets = sorted([public_password_reset_request(req) for req in read_password_reset_requests()["requests"] if req.get("status") == "pending"], key=lambda item: str(item.get("createdAt")))
    return jsonify({"pendingUsers": pending_users, "reactivationRequests": reactivations, "passwordResetRequests": resets, "notificationCount": len(pending_users) + len(reactivations) + len(resets)})


def admin_settings_summary():
    keys = read_keys()
    users = read_users()["users"]
    reactivation_requests = read_reactivation_requests()["requests"]
    password_reset_requests = read_password_reset_requests()["requests"]
    used_keys = sum(1 for entry in keys if entry.get("redeemedAt"))
    return {
        "keys": {
            "total": len(keys),
            "free": len(keys) - used_keys,
            "used": used_keys,
        },
        "users": {
            "total": len(users),
            "approved": sum(1 for user in users if user.get("status") == "approved"),
            "pending": sum(1 for user in users if user.get("status") == "pending"),
            "rejected": sum(1 for user in users if user.get("status") == "rejected"),
        },
        "requests": {
            "pendingReactivations": sum(1 for req in reactivation_requests if req.get("status") == "pending"),
            "pendingPasswordResets": sum(1 for req in password_reset_requests if req.get("status") == "pending"),
            "resolvedReactivations": sum(1 for req in reactivation_requests if req.get("status") != "pending"),
            "resolvedPasswordResets": sum(1 for req in password_reset_requests if req.get("status") != "pending"),
        },
    }


@app.get("/api/admin/settings")
def admin_settings():
    admin, error = require_admin()
    if error:
        return error
    return jsonify(admin_settings_summary())


@app.get("/api/admin/info")
def admin_info():
    admin, error = require_admin()
    if error:
        return error
    setup_state = setup_status_payload()
    return jsonify({
        "app": {
            "id": APP_ID,
            "name": APP_NAME,
            "subtitle": APP_SUBTITLE,
            "version": APP_VERSION,
            "buildDate": APP_BUILD_DATE,
            "gitSha": APP_GIT_SHA,
        },
        "runtime": {
            "dataDir": str(DATA_DIR),
            "csvPath": str(CSV_PATH),
            "publicDir": str(PUBLIC_DIR),
            "logLevel": os.environ.get("ISHIKU_LOG_LEVEL", "info"),
            "trustProxy": str(os.environ.get("ISHIKU_TRUST_PROXY", "false")),
        },
        "health": {
            "status": "ready" if setup_state.get("setupConfigured") or setup_state.get("setupCompleted") else "setup_unconfigured",
            "setup": setup_state,
            "database": "file-json-csv",
        },
    })


@app.post("/api/admin/maintenance/delete-used-keys")
def admin_delete_used_keys():
    admin, error = require_admin()
    if error:
        return error
    with file_lock:
        keys = read_keys()
        kept = [entry for entry in keys if not entry.get("redeemedAt")]
        removed = len(keys) - len(kept)
        if removed:
            write_keys(kept)
    return jsonify({"ok": True, "removed": removed, "summary": admin_settings_summary()})


@app.post("/api/admin/maintenance/reactivate-used-keys")
def admin_reactivate_used_keys():
    admin, error = require_admin()
    if error:
        return error
    with file_lock:
        keys = read_keys()
        changed = 0
        for entry in keys:
            if entry.get("redeemedAt"):
                entry["redeemedAt"] = ""
                entry["redeemedBy"] = ""
                entry["redeemedByName"] = ""
                changed += 1
        if changed:
            write_keys(keys)
    return jsonify({"ok": True, "changed": changed, "summary": admin_settings_summary()})


@app.post("/api/admin/maintenance/clear-resolved-requests")
def admin_clear_resolved_requests():
    admin, error = require_admin()
    if error:
        return error
    with file_lock:
        reactivation_data = read_reactivation_requests()
        password_data = read_password_reset_requests()
        reactivation_pending = [req for req in reactivation_data["requests"] if req.get("status") == "pending"]
        password_pending = [req for req in password_data["requests"] if req.get("status") == "pending"]
        removed = (len(reactivation_data["requests"]) - len(reactivation_pending)) + (len(password_data["requests"]) - len(password_pending))
        reactivation_data["requests"] = reactivation_pending
        password_data["requests"] = password_pending
        write_reactivation_requests(reactivation_data)
        write_password_reset_requests(password_data)
    return jsonify({"ok": True, "removed": removed, "summary": admin_settings_summary()})


@app.post("/api/admin/users/<user_id>/approve")
def admin_user_approve(user_id):
    admin, error = require_admin()
    if error:
        return error
    with file_lock:
        data = read_users()
        user = next((candidate for candidate in data["users"] if candidate.get("id") == user_id), None)
        if not user:
            return jsonify({"error": "User not found"}), 404
        user["status"] = "approved"
        user["role"] = user.get("role") or "user"
        user["approvedAt"] = now_iso()
        user["approvedBy"] = admin["id"]
        write_users(data)
    audit_event("admin.user_approved", actor=admin["id"], target=user["id"])
    return jsonify({"ok": True, "user": public_user(user)})


@app.post("/api/admin/users/<user_id>/reject")
def admin_user_reject(user_id):
    admin, error = require_admin()
    if error:
        return error
    if user_id == admin.get("id"):
        return jsonify({"error": "You cannot reject your own admin account."}), 400
    with file_lock:
        data = read_users()
        user = next((candidate for candidate in data["users"] if candidate.get("id") == user_id), None)
        if not user:
            return jsonify({"error": "User not found"}), 404
        user["status"] = "rejected"
        user["rejectedAt"] = now_iso()
        user["rejectedBy"] = admin["id"]
        write_users(data)
    revoke_sessions(user["id"])
    audit_event("admin.user_rejected", actor=admin["id"], target=user["id"])
    return jsonify({"ok": True, "user": public_user(user)})


@app.get("/api/admin/users")
def admin_users_list():
    admin, error = require_admin()
    if error:
        return error
    users = sorted([public_user(user) for user in read_users()["users"]], key=lambda item: str(item.get("username")))
    return jsonify({"users": users})


@app.post("/api/admin/users")
def admin_user_create():
    admin, error = require_admin()
    if error:
        return error
    body = json_body()
    username = normalize_username(body.get("username"))
    password = str(body.get("password") or "")
    credential_error = validate_credentials(username, password, min_password_length=12)
    if credential_error:
        return jsonify({"error": credential_error}), 400
    display_name = str(body.get("displayName") or username).strip()
    email = str(body.get("email") or "").strip()
    role = "admin" if body.get("role") == "admin" else "user"
    if not display_name or len(display_name) > 80:
        return jsonify({"error": "Display name is required and must be at most 80 characters."}), 400
    if len(email) > 180:
        return jsonify({"error": "Email address is too long."}), 400
    if password.strip().lower() in PLACEHOLDER_PASSWORDS or password.strip().lower() in {username, APP_ID, APP_NAME.lower()}:
        return jsonify({"error": "Please choose a stronger password."}), 400
    with file_lock:
        data = read_users()
        if any(user.get("username") == username for user in data["users"]):
            return jsonify({"error": "This username is already taken."}), 409
        hashed = hash_password(password)
        created = now_iso()
        user = {
            "id": secrets.token_urlsafe(24),
            "username": username,
            "displayName": display_name,
            "email": email,
            "passwordHash": hashed["hash"],
            "passwordAlgorithm": hashed["algorithm"],
            "role": role,
            "status": "approved",
            "createdAt": created,
            "approvedAt": created,
            "approvedBy": admin["id"],
        }
        data["users"].append(user)
        write_users(data)
    audit_event("admin.user_created", actor=admin["id"], target=user["id"])
    return jsonify({"ok": True, "user": public_user(user)}), 201


def set_user_password(user, password, admin_id):
    hashed = hash_password(password)
    user["passwordHash"] = hashed["hash"]
    user["passwordAlgorithm"] = hashed["algorithm"]
    user.pop("salt", None)
    user.pop("iterations", None)
    user["passwordChangedAt"] = now_iso()
    user["passwordChangedBy"] = admin_id


@app.post("/api/admin/password-reset-requests/<request_id>/complete")
def admin_password_reset_complete(request_id):
    admin, error = require_admin()
    if error:
        return error
    body = json_body()
    error_text = validate_password(body.get("password"), min_length=12)
    if error_text:
        return jsonify({"error": error_text}), 400
    with file_lock:
        reset_data = read_password_reset_requests()
        reset_request = next((candidate for candidate in reset_data["requests"] if candidate.get("id") == request_id), None)
        if not reset_request:
            return jsonify({"error": "Password reset request not found"}), 404
        if reset_request.get("status") != "pending":
            return jsonify({"error": "Request has already been resolved"}), 409
        user_data = read_users()
        user = next((candidate for candidate in user_data["users"] if candidate.get("id") == reset_request.get("userId")), None)
        if not user:
            return jsonify({"error": "User not found"}), 404
        set_user_password(user, body.get("password"), admin["id"])
        reset_request["status"] = "completed"
        reset_request["resolvedAt"] = now_iso()
        reset_request["resolvedBy"] = admin["id"]
        write_users(user_data)
        write_password_reset_requests(reset_data)
    revoke_sessions(user["id"])
    audit_event("admin.password_reset_completed", actor=admin["id"], target=user["id"])
    return jsonify({"ok": True, "request": public_password_reset_request(reset_request), "user": public_user(user)})


@app.post("/api/admin/password-reset-requests/<request_id>/reject")
def admin_password_reset_reject(request_id):
    admin, error = require_admin()
    if error:
        return error
    with file_lock:
        data = read_password_reset_requests()
        reset_request = next((candidate for candidate in data["requests"] if candidate.get("id") == request_id), None)
        if not reset_request:
            return jsonify({"error": "Password reset request not found"}), 404
        if reset_request.get("status") != "pending":
            return jsonify({"error": "Request has already been resolved"}), 409
        reset_request["status"] = "rejected"
        reset_request["resolvedAt"] = now_iso()
        reset_request["resolvedBy"] = admin["id"]
        write_password_reset_requests(data)
    return jsonify({"ok": True, "request": public_password_reset_request(reset_request)})


@app.get("/api/keys")
def api_keys():
    user, error = require_auth()
    if error:
        return error
    include_audit = user.get("role") == "admin"
    response = jsonify({"keys": [public_key(entry, index, include_audit) for index, entry in enumerate(read_keys())]})
    response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/api/keys/<int:index>/secret")
def api_key_secret(index):
    user, error = require_auth()
    if error:
        return error
    keys = read_keys()
    if index < 0 or index >= len(keys):
        return jsonify({"error": "Key not found"}), 404
    entry = keys[index]
    if not entry.get("key"):
        return jsonify({"error": "This row does not contain a key"}), 422
    return jsonify({"ok": True, "key": entry["key"], "redeemUrl": steam_redeem_url(entry["key"])})


@app.post("/api/keys/<int:index>/share")
def api_key_share(index):
    user, error = require_auth()
    if error:
        return error
    keys = read_keys()
    if index < 0 or index >= len(keys):
        return jsonify({"error": "Key not found"}), 404
    entry = keys[index]
    if not entry.get("key"):
        return jsonify({"error": "This row does not contain a key"}), 422
    token = share_token_for_key(entry["key"])
    return jsonify({"ok": True, "token": token, "shareUrl": f"{public_base_url()}/share/{quote(token)}"})


@app.post("/api/keys/<int:index>/reactivation-request")
def api_key_reactivation_request(index):
    user, error = require_auth()
    if error:
        return error
    keys = read_keys()
    if index < 0 or index >= len(keys):
        return jsonify({"error": "Key not found"}), 404
    entry = keys[index]
    if not entry.get("redeemedAt"):
        return jsonify({"error": "Key is already free"}), 409
    fingerprint = key_fingerprint(entry.get("key", ""))
    with file_lock:
        data = read_reactivation_requests()
        exists = any(req.get("status") == "pending" and safe_equal(req.get("keyFingerprint", ""), fingerprint) for req in data["requests"])
        if exists:
            return jsonify({"error": "There is already a pending request for this key."}), 409
        req = {
            "id": secrets.token_urlsafe(24),
            "index": index,
            "game": entry.get("game"),
            "keyFingerprint": fingerprint,
            "requestedBy": user["id"],
            "requestedByName": user["username"],
            "status": "pending",
            "createdAt": now_iso(),
        }
        data["requests"].append(req)
        write_reactivation_requests(data)
    return jsonify({"ok": True, "request": public_reactivation_request(req)}), 201


@app.post("/api/admin/reactivation-requests/<request_id>/approve")
def admin_reactivation_approve(request_id):
    admin, error = require_admin()
    if error:
        return error
    with file_lock:
        data = read_reactivation_requests()
        req = next((candidate for candidate in data["requests"] if candidate.get("id") == request_id), None)
        if not req:
            return jsonify({"error": "Request not found"}), 404
        if req.get("status") != "pending":
            return jsonify({"error": "Request has already been resolved"}), 409
        keys = read_keys()
        index, entry = find_key_by_request(keys, req)
        if entry is None:
            return jsonify({"error": "Key for this request was not found"}), 404
        keys[index] = {**entry, "redeemedAt": "", "redeemedBy": "", "redeemedByName": ""}
        req["status"] = "approved"
        req["resolvedAt"] = now_iso()
        req["resolvedBy"] = admin["id"]
        req["resolvedIndex"] = index
        write_keys(keys)
        write_reactivation_requests(data)
    return jsonify({"ok": True, "request": public_reactivation_request(req), "key": public_key(keys[index], index, True)})


@app.post("/api/admin/reactivation-requests/<request_id>/reject")
def admin_reactivation_reject(request_id):
    admin, error = require_admin()
    if error:
        return error
    with file_lock:
        data = read_reactivation_requests()
        req = next((candidate for candidate in data["requests"] if candidate.get("id") == request_id), None)
        if not req:
            return jsonify({"error": "Request not found"}), 404
        if req.get("status") != "pending":
            return jsonify({"error": "Request has already been resolved"}), 409
        req["status"] = "rejected"
        req["resolvedAt"] = now_iso()
        req["resolvedBy"] = admin["id"]
        write_reactivation_requests(data)
    return jsonify({"ok": True, "request": public_reactivation_request(req)})


@app.post("/api/admin/keys")
def admin_key_create():
    admin, error = require_admin()
    if error:
        return error
    body = json_body()
    with file_lock:
        keys = read_keys()
        entry = clean_key_entry({"game": body.get("game"), "key": body.get("key"), "redeemedAt": body.get("redeemedAt") or "", "addedAt": body.get("addedAt") or now_iso()})
        error_text = validate_key_entry(entry)
        if error_text:
            return jsonify({"error": error_text}), 400
        keys.append(entry)
        write_keys(keys)
    return jsonify({"ok": True, "key": public_key(entry, len(keys) - 1)}), 201


@app.patch("/api/admin/keys/<int:index>")
def admin_key_update(index):
    admin, error = require_admin()
    if error:
        return error
    with file_lock:
        keys = read_keys()
        if index < 0 or index >= len(keys):
            return jsonify({"error": "Key not found"}), 404
        entry = clean_key_entry(json_body(), keys[index])
        error_text = validate_key_entry(entry)
        if error_text:
            return jsonify({"error": error_text}), 400
        keys[index] = entry
        write_keys(keys)
    return jsonify({"ok": True, "key": public_key(entry, index)})


@app.delete("/api/admin/keys/<int:index>")
def admin_key_delete(index):
    admin, error = require_admin()
    if error:
        return error
    with file_lock:
        keys = read_keys()
        if index < 0 or index >= len(keys):
            return jsonify({"error": "Key not found"}), 404
        removed = keys.pop(index)
        write_keys(keys)
    return jsonify({"ok": True, "removed": public_key(removed, index)})


@app.post("/api/redeem/<int:index>")
def api_redeem(index):
    user, error = require_auth()
    if error:
        return error
    with file_lock:
        keys = read_keys()
        if index < 0 or index >= len(keys):
            return jsonify({"error": "Key not found"}), 404
        entry = keys[index]
        if entry.get("redeemedAt"):
            return jsonify({"error": "Key is already used"}), 409
        if not entry.get("key"):
            return jsonify({"error": "This row does not contain a key"}), 422
        redeemed_at = now_iso()
        keys[index] = {**entry, "redeemedAt": redeemed_at, "redeemedBy": user.get("id", ""), "redeemedByName": user.get("username", "")}
        write_keys(keys)
    return jsonify({"ok": True, "game": entry.get("game"), "redeemedAt": redeemed_at, "redeemedByName": user.get("username"), "redeemUrl": steam_redeem_url(entry.get("key"))})


@app.post("/api/unredeem/<int:index>")
def api_unredeem(index):
    admin, error = require_admin()
    if error:
        return error
    with file_lock:
        keys = read_keys()
        if index < 0 or index >= len(keys):
            return jsonify({"error": "Key not found"}), 404
        entry = keys[index]
        if not entry.get("redeemedAt"):
            return jsonify({"error": "Key is not used"}), 409
        keys[index] = {**entry, "redeemedAt": "", "redeemedBy": "", "redeemedByName": ""}
        write_keys(keys)
    return jsonify({"ok": True, "index": index, "game": entry.get("game")})


@app.get("/api/share/<token>")
def api_share(token):
    found = next((entry for entry in read_keys() if entry.get("key") and safe_equal(share_token_for_key(entry["key"]), token)), None)
    if not found:
        return jsonify({"error": "Share link not found"}), 404
    response = jsonify({
        "ok": True,
        "game": found.get("game"),
        "key": found.get("key"),
        "redeemed": bool(found.get("redeemedAt")),
        "redeemedAt": found.get("redeemedAt") or None,
        "addedAt": found.get("addedAt") or None,
        "redeemUrl": steam_redeem_url(found.get("key")),
        "steamUrl": steam_search_url(found.get("game")),
        "steamDbUrl": steamdb_url(found.get("game")),
    })
    response.headers["Cache-Control"] = "no-store"
    return response


def send_public(filename):
    response = send_from_directory(PUBLIC_DIR, filename)
    if filename.endswith((".html", ".js", ".css")):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/")
def index():
    return send_public("index.html")


@app.get("/login")
def login_page():
    return send_public("index.html")


@app.get("/setup")
def setup_page():
    return send_public("index.html")


@app.get("/admin")
def admin_page():
    return send_public("index.html")


@app.get("/share/<token>")
def share_page(token):
    return send_public("share.html")


@app.get("/<path:filename>")
def public_file(filename):
    return send_public(filename)


def init_storage():
    with file_lock:
        ensure_csv()
        if not USERS_PATH.exists():
            write_users({"users": []})
        if not REQUESTS_PATH.exists():
            write_reactivation_requests({"requests": []})
        if not PASSWORD_RESET_REQUESTS_PATH.exists():
            write_password_reset_requests({"requests": []})
        if not SESSIONS_PATH.exists():
            write_sessions({"sessions": []})
        if not SETUP_STATE_PATH.exists():
            write_setup_state({"setupCompleted": admin_exists(read_users()["users"]), "createdAt": now_iso()})


init_storage()


if __name__ == "__main__":
    print(f"{APP_NAME} Python running on http://0.0.0.0:{PORT}")
    print(f"CSV: {CSV_PATH}")
    print(f"Users: {USERS_PATH}")
    print(f"Public: {PUBLIC_DIR}")
    app.run(host="0.0.0.0", port=PORT)
