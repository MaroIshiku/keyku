import hashlib
import importlib.util
import json
import stat
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest


SETUP_SECRET = "synthetic-unit-test-setup-secret-123456"
ADMIN_PASSWORD = "synthetic-admin-password-123456"


@pytest.fixture
def keyku(tmp_path, monkeypatch):
    monkeypatch.setenv("ISHIKU_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ISHIKU_SETUP_SECRET", SETUP_SECRET)
    monkeypatch.setenv("PUBLIC_DIR", str(Path(__file__).resolve().parents[1] / "public"))
    monkeypatch.setenv("ISHIKU_COOKIE_SECURE", "false")
    module_name = f"keyku_test_{uuid.uuid4().hex}"
    source = Path(__file__).resolve().parents[1] / "python" / "app.py"
    spec = importlib.util.spec_from_file_location(module_name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    module.app.config.update(TESTING=True)
    yield module
    sys.modules.pop(module_name, None)


def setup_admin(client):
    response = client.post(
        "/api/setup/register-admin",
        json={
            "setupSecret": SETUP_SECRET,
            "displayName": "Synthetic Admin",
            "adminUsername": "admin-user",
            "password": ADMIN_PASSWORD,
            "passwordConfirm": ADMIN_PASSWORD,
        },
    )
    assert response.status_code == 201
    return response.headers["X-CSRF-Token"], response.get_json()["user"]


def legacy_hash(module, password, salt="synthetic-salt", iterations=310000):
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iterations, dklen=32)
    return {"passwordHash": module.b64url(digest), "salt": salt, "iterations": iterations}


def test_setup_uses_argon2_and_csrf_protects_mutations(keyku):
    client = keyku.app.test_client()
    csrf, user = setup_admin(client)

    stored = keyku.read_users()["users"][0]
    assert stored["passwordAlgorithm"] == "argon2id"
    assert stored["passwordHash"].startswith("$argon2id$")
    assert "salt" not in stored and "iterations" not in stored
    assert SETUP_SECRET not in json.dumps(keyku.read_users())
    assert client.post("/api/setup/register-admin", json={}).status_code == 409

    denied = client.post("/api/admin/keys", json={"game": "Synthetic Game", "key": "AAAA-BBBB-CCCC"})
    assert denied.status_code == 403
    denied_payload = denied.get_json()
    assert denied_payload["error"] == "Request verification failed. Refresh the page and try again."
    assert denied_payload["message"] == denied_payload["error"]
    assert denied_payload["code"] == "forbidden"
    assert len(denied_payload["requestId"]) == 24
    created = client.post(
        "/api/admin/keys",
        json={"game": "Synthetic Game", "key": "AAAA-BBBB-CCCC"},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 201
    listed = client.get("/api/keys").get_json()["keys"]
    assert listed == [{"addedAt": created.get_json()["key"]["addedAt"], "game": "Synthetic Game", "index": 0, "redeemed": False, "redeemedAt": None, "redeemedBy": None, "redeemedByName": None}]
    assert "key" not in listed[0]
    assert client.get("/api/keys/0/secret").get_json()["key"] == "AAAA-BBBB-CCCC"
    assert user["role"] == "admin"
    assert stat.S_IMODE(keyku.AUDIT_PATH.stat().st_mode) == 0o600


def test_login_is_generic_rate_limited_and_upgrades_legacy_pbkdf2(keyku):
    approved = {
        "id": "legacy-user-id",
        "username": "legacy-user",
        "displayName": "Legacy User",
        "role": "user",
        "status": "approved",
        **legacy_hash(keyku, "legacy-password-123456"),
    }
    pending = {
        "id": "pending-user-id",
        "username": "pending-user",
        "displayName": "Pending User",
        "role": "user",
        "status": "pending",
        **legacy_hash(keyku, "pending-password-123456"),
    }
    keyku.write_users({"users": [approved, pending]})
    keyku.write_setup_state({"setupCompleted": True})
    client = keyku.app.test_client()

    missing = client.post("/api/auth/login", json={"username": "missing-user", "password": "wrong"})
    inactive = client.post("/api/auth/login", json={"username": "pending-user", "password": "pending-password-123456"})
    assert missing.status_code == inactive.status_code == 401
    assert missing.get_json()["error"] == inactive.get_json()["error"] == "Username or password is incorrect."
    assert missing.get_json()["code"] == inactive.get_json()["code"] == "authentication_required"
    assert missing.get_json()["message"] == inactive.get_json()["message"] == "Username or password is incorrect."
    assert missing.get_json()["requestId"] != inactive.get_json()["requestId"]

    logged_in = client.post("/api/auth/login", json={"username": "legacy-user", "password": "legacy-password-123456"})
    assert logged_in.status_code == 200
    assert logged_in.headers["X-CSRF-Token"]
    upgraded = keyku.read_users()["users"][0]
    assert upgraded["passwordAlgorithm"] == "argon2id"
    assert upgraded["passwordHash"].startswith("$argon2id$")
    assert "salt" not in upgraded and "iterations" not in upgraded

    for _ in range(keyku.LOGIN_ACCOUNT_LIMIT):
        response = client.post("/api/auth/login", json={"username": "rate-user", "password": "wrong"})
        assert response.status_code == 401
    limited = client.post("/api/auth/login", json={"username": "rate-user", "password": "wrong"})
    assert limited.status_code == 429


def test_sessions_are_listed_revocable_and_expire(keyku):
    first = keyku.app.test_client()
    first_csrf, _user = setup_admin(first)
    second = keyku.app.test_client()
    login = second.post("/api/auth/login", json={"username": "admin-user", "password": ADMIN_PASSWORD})
    assert login.status_code == 200
    second_csrf = login.headers["X-CSRF-Token"]

    sessions = second.get("/api/auth/sessions").get_json()["sessions"]
    assert len(sessions) == 2
    other = next(item for item in sessions if not item["current"])
    revoked = second.delete(f"/api/auth/sessions/{other['id']}", headers={"X-CSRF-Token": second_csrf})
    assert revoked.status_code == 200
    assert first.get("/api/keys").status_code == 401
    assert second.get("/api/keys").status_code == 200

    with keyku.file_lock:
        data = keyku.read_sessions()
        data["sessions"][0]["idleExpiresAt"] = keyku.iso_at(datetime.now(timezone.utc) - timedelta(seconds=1))
        keyku.write_sessions(data)
    assert second.get("/api/auth/me").get_json()["authenticated"] is False
    assert first_csrf


def test_cross_site_and_oversized_requests_fail_closed(keyku):
    client = keyku.app.test_client()
    csrf, _user = setup_admin(client)
    cross_site = client.post(
        "/api/admin/keys",
        json={"game": "Synthetic Game", "key": "AAAA-BBBB-CCCC"},
        headers={"Origin": "https://attacker.example", "X-CSRF-Token": csrf},
    )
    assert cross_site.status_code == 403
    oversized = client.post(
        "/api/admin/keys",
        data=json.dumps({"game": "x" * 70000, "key": "AAAA-BBBB-CCCC"}),
        content_type="application/json",
        headers={"X-CSRF-Token": csrf},
    )
    assert oversized.status_code == 413


def test_short_setup_secret_is_rejected_without_blocking_existing_install(tmp_path, monkeypatch):
    monkeypatch.setenv("ISHIKU_DATA_DIR", str(tmp_path / "data"))
    monkeypatch.setenv("ISHIKU_SETUP_SECRET", "too-short")
    monkeypatch.setenv("PUBLIC_DIR", str(Path(__file__).resolve().parents[1] / "public"))
    monkeypatch.setenv("ISHIKU_COOKIE_SECURE", "false")
    module_name = f"keyku_test_{uuid.uuid4().hex}"
    source = Path(__file__).resolve().parents[1] / "python" / "app.py"
    spec = importlib.util.spec_from_file_location(module_name, source)
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    module.app.config.update(TESTING=True)
    try:
        client = module.app.test_client()
        status = client.get("/api/setup/status").get_json()
        assert status["setupRequired"] is True
        assert status["setupConfigured"] is False
        assert status["message"] == "ISHIKU_SETUP_SECRET must contain at least 32 characters."
        assert client.get("/readyz").status_code == 503

        module.write_users({"users": [{
            "id": "legacy-admin",
            "username": "legacy-admin",
            "displayName": "Legacy Admin",
            "role": "admin",
            "status": "approved",
            **module.hash_password("legacy-admin-password-123456"),
        }]})
        module.write_setup_state({"setupCompleted": True})
        assert client.get("/readyz").status_code == 200
    finally:
        sys.modules.pop(module_name, None)


def test_password_change_revokes_other_sessions_and_rotates_current(keyku):
    first = keyku.app.test_client()
    first_csrf, user = setup_admin(first)
    second = keyku.app.test_client()
    login = second.post("/api/auth/login", json={"username": "admin-user", "password": ADMIN_PASSWORD})
    assert login.status_code == 200

    new_password = "synthetic-new-password-123456"
    changed = first.patch(
        "/api/account",
        json={
            "displayName": user["displayName"],
            "username": user["username"],
            "email": "",
            "currentPassword": ADMIN_PASSWORD,
            "newPassword": new_password,
            "passwordConfirm": new_password,
        },
        headers={"X-CSRF-Token": first_csrf},
    )
    assert changed.status_code == 200
    assert changed.get_json()["sessionRotated"] is True
    assert changed.headers["X-CSRF-Token"] != first_csrf
    assert second.get("/api/keys").status_code == 401
    assert first.get("/api/keys").status_code == 200
