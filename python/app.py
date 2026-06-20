import base64
import csv
import hashlib
import hmac
import json
import os
import secrets
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from urllib.parse import quote

from flask import Flask, jsonify, make_response, request, send_from_directory
from werkzeug.middleware.proxy_fix import ProxyFix


PORT = int(os.environ.get("PORT", "3000"))
CSV_PATH = Path(os.environ.get("CSV_PATH", "/app/data/keys.csv"))
DATA_DIR = CSV_PATH.parent
USERS_PATH = Path(os.environ.get("USERS_PATH", str(DATA_DIR / "users.json")))
REQUESTS_PATH = Path(os.environ.get("REACTIVATION_REQUESTS_PATH", str(DATA_DIR / "reactivation-requests.json")))
PASSWORD_RESET_REQUESTS_PATH = Path(os.environ.get("PASSWORD_RESET_REQUESTS_PATH", str(DATA_DIR / "password-reset-requests.json")))
SECRET_PATH = Path(os.environ.get("SESSION_SECRET_FILE", str(DATA_DIR / "session-secret.txt")))
PUBLIC_DIR = Path(os.environ.get("PUBLIC_DIR", str(Path(__file__).resolve().parent.parent / "public")))

SESSION_COOKIE = "steam_keys_session"
SESSION_TTL_SECONDS = 14 * 24 * 60 * 60
SESSION_TTL_MS = SESSION_TTL_SECONDS * 1000

app = Flask(__name__, static_folder=None)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
file_lock = RLock()


def now_iso():
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


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


def b64url_json(value):
    return b64url(json.dumps(value, separators=(",", ":")).encode("utf-8"))


def sign_payload(payload):
    return b64url(hmac.new(SESSION_SECRET.encode("utf-8"), payload.encode("utf-8"), hashlib.sha256).digest())


def safe_equal(left, right):
    return hmac.compare_digest(str(left), str(right))


def public_user(user):
    return {
        "id": user.get("id"),
        "username": user.get("username"),
        "role": user.get("role"),
        "status": user.get("status"),
        "createdAt": user.get("createdAt"),
        "approvedAt": user.get("approvedAt"),
    }


def normalize_username(username):
    return str(username or "").strip().lower()


def validate_password(password):
    clean = str(password or "")
    if len(clean) < 10 or len(clean) > 200:
        return "Password must be 10 to 200 characters."
    return None


def validate_credentials(username, password):
    clean_username = normalize_username(username)
    allowed = "abcdefghijklmnopqrstuvwxyz0123456789._-"
    if len(clean_username) < 3 or len(clean_username) > 32 or any(ch not in allowed for ch in clean_username):
        return "Username must be 3-32 characters and may contain a-z, 0-9, dot, underscore, and hyphen."
    return validate_password(password)


def hash_password(password, salt=None, iterations=310000):
    clean_salt = salt or secrets.token_urlsafe(16)
    digest = hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), clean_salt.encode("utf-8"), int(iterations), dklen=32)
    return {"salt": clean_salt, "iterations": int(iterations), "hash": b64url(digest)}


def verify_password(password, user):
    if not user:
        return False
    expected = user.get("passwordHash", "")
    actual = hash_password(password, user.get("salt", ""), user.get("iterations", 310000))["hash"]
    return safe_equal(actual, expected)


def read_users():
    data = read_json(USERS_PATH, {"users": []})
    return data if isinstance(data.get("users"), list) else {"users": []}


def write_users(data):
    write_json(USERS_PATH, data)


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


def cookie_secure():
    return request.is_secure or request.headers.get("X-Forwarded-Proto", "").split(",")[0].strip() == "https"


def set_session_cookie(response, user):
    payload = b64url_json({"uid": user["id"], "exp": int(datetime.now().timestamp() * 1000) + SESSION_TTL_MS})
    token = f"{payload}.{sign_payload(payload)}"
    response.set_cookie(
        SESSION_COOKIE,
        token,
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=cookie_secure(),
        samesite="Lax",
        path="/",
    )
    return response


def clear_session_cookie(response):
    response.set_cookie(SESSION_COOKIE, "", max_age=0, httponly=True, samesite="Lax", path="/")
    return response


def current_user():
    token = request.cookies.get(SESSION_COOKIE)
    if not token or "." not in token:
        return None
    payload, signature = token.rsplit(".", 1)
    if not safe_equal(sign_payload(payload), signature):
        return None
    try:
        padded = payload + "=" * (-len(payload) % 4)
        parsed = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
    except Exception:
        return None
    if not parsed.get("uid") or int(parsed.get("exp", 0)) < int(datetime.now().timestamp() * 1000):
        return None
    user = next((candidate for candidate in read_users()["users"] if candidate.get("id") == parsed["uid"]), None)
    if not user or user.get("status") != "approved":
        return None
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
        CSV_PATH.write_text("Game,Key,RedeemedAt,addedAt\n", encoding="utf-8")


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
        })
    return keys


def write_keys(keys):
    ensure_csv()
    delimiter = ","
    if CSV_PATH.exists():
        delimiter = detect_delimiter(CSV_PATH.read_text(encoding="utf-8-sig"))
    output = tempfile.SpooledTemporaryFile(mode="w+", encoding="utf-8", newline="")
    writer = csv.DictWriter(output, fieldnames=["game", "key", "redeemedAt", "addedAt"], delimiter=delimiter)
    output.write(delimiter.join(["Game", "Key", "RedeemedAt", "addedAt"]) + "\n")
    for entry in keys:
        writer.writerow({
            "game": entry.get("game", ""),
            "key": entry.get("key", ""),
            "redeemedAt": entry.get("redeemedAt", ""),
            "addedAt": entry.get("addedAt", ""),
        })
    output.seek(0)
    atomic_write(CSV_PATH, output.read())
    output.close()


def clean_key_entry(data, existing=None):
    existing = existing or {}
    return {
        "game": str(data.get("game", existing.get("game", "")) or "").strip(),
        "key": str(data.get("key", existing.get("key", "")) or "").strip(),
        "redeemedAt": str(data.get("redeemedAt", existing.get("redeemedAt", "")) or "").strip(),
        "addedAt": str(data.get("addedAt", existing.get("addedAt", "")) or "").strip(),
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
    configured = (os.environ.get("PUBLIC_BASE_URL") or os.environ.get("APP_BASE_URL") or "").strip().rstrip("/")
    if configured:
        return configured
    proto = request.headers.get("X-Forwarded-Proto") or request.scheme
    host = request.headers.get("X-Forwarded-Host") or request.host
    return f"{proto.split(',')[0].strip()}://{host}"


def public_key(entry, index):
    return {
        "index": index,
        "game": entry.get("game", ""),
        "redeemed": bool(entry.get("redeemedAt")),
        "redeemedAt": entry.get("redeemedAt") or None,
        "addedAt": entry.get("addedAt") or None,
    }


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
    return request.get_json(silent=True) or {}


@app.after_request
def security_headers(response):
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["Referrer-Policy"] = "same-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    return response


@app.get("/api/auth/me")
def auth_me():
    user = current_user()
    if not user:
        return jsonify({"authenticated": False})
    users = read_users()["users"]
    pending_users = sum(1 for candidate in users if candidate.get("status") == "pending")
    pending_reactivations = sum(1 for req in read_reactivation_requests()["requests"] if req.get("status") == "pending")
    pending_resets = sum(1 for req in read_password_reset_requests()["requests"] if req.get("status") == "pending")
    count = pending_users + pending_reactivations + pending_resets if user.get("role") == "admin" else 0
    return jsonify({"authenticated": True, "user": public_user(user), "pendingCount": pending_users if user.get("role") == "admin" else 0, "notificationCount": count})


@app.post("/api/auth/register")
def auth_register():
    body = json_body()
    error = validate_credentials(body.get("username"), body.get("password"))
    if error:
        return jsonify({"error": error}), 400
    username = normalize_username(body.get("username"))
    with file_lock:
        data = read_users()
        if any(user.get("username") == username for user in data["users"]):
            return jsonify({"error": "This username is already taken."}), 409
        first_user = len(data["users"]) == 0
        hashed = hash_password(body.get("password"))
        created = now_iso()
        user = {
            "id": secrets.token_urlsafe(24),
            "username": username,
            "passwordHash": hashed["hash"],
            "salt": hashed["salt"],
            "iterations": hashed["iterations"],
            "role": "admin" if first_user else "user",
            "status": "approved" if first_user else "pending",
            "createdAt": created,
            "approvedAt": created if first_user else None,
            "approvedBy": "bootstrap" if first_user else None,
        }
        data["users"].append(user)
        write_users(data)
    response = make_response(jsonify({
        "ok": True,
        "authenticated": first_user,
        "message": "Admin account created. Future registrations must be approved." if first_user else "Registration saved. An admin must approve access.",
        "user": public_user(user),
    }), 201 if first_user else 202)
    if first_user:
        set_session_cookie(response, user)
    return response


@app.post("/api/auth/login")
def auth_login():
    body = json_body()
    username = normalize_username(body.get("username"))
    password = str(body.get("password") or "")
    user = next((candidate for candidate in read_users()["users"] if candidate.get("username") == username), None)
    if not user or not verify_password(password, user):
        return jsonify({"error": "Username or password is incorrect."}), 401
    if user.get("status") == "pending":
        return jsonify({"error": "Your account is waiting for admin approval."}), 403
    if user.get("status") != "approved":
        return jsonify({"error": "This account is not active."}), 403
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
    response = make_response(jsonify({"ok": True}))
    return clear_session_cookie(response)


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
    return jsonify({"ok": True, "user": public_user(user)})


def set_user_password(user, password, admin_id):
    hashed = hash_password(password)
    user["passwordHash"] = hashed["hash"]
    user["salt"] = hashed["salt"]
    user["iterations"] = hashed["iterations"]
    user["passwordChangedAt"] = now_iso()
    user["passwordChangedBy"] = admin_id


@app.post("/api/admin/password-reset-requests/<request_id>/complete")
def admin_password_reset_complete(request_id):
    admin, error = require_admin()
    if error:
        return error
    body = json_body()
    error_text = validate_password(body.get("password"))
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
    response = jsonify({"keys": [public_key(entry, index) for index, entry in enumerate(read_keys())]})
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
        keys[index] = {**entry, "redeemedAt": ""}
        req["status"] = "approved"
        req["resolvedAt"] = now_iso()
        req["resolvedBy"] = admin["id"]
        req["resolvedIndex"] = index
        write_keys(keys)
        write_reactivation_requests(data)
    return jsonify({"ok": True, "request": public_reactivation_request(req), "key": public_key(keys[index], index)})


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
        keys[index] = {**entry, "redeemedAt": redeemed_at}
        write_keys(keys)
    return jsonify({"ok": True, "game": entry.get("game"), "redeemedAt": redeemed_at, "redeemUrl": steam_redeem_url(entry.get("key"))})


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
        keys[index] = {**entry, "redeemedAt": ""}
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


init_storage()


if __name__ == "__main__":
    print(f"Steam Key Vault Python running on http://0.0.0.0:{PORT}")
    print(f"CSV: {CSV_PATH}")
    print(f"Users: {USERS_PATH}")
    print(f"Public: {PUBLIC_DIR}")
    app.run(host="0.0.0.0", port=PORT)
