#!/bin/sh
set -eu

SCRIPT_DIR=$(dirname -- "$0")
ROOT=$(CDPATH='' cd -- "$SCRIPT_DIR/.." && pwd)
COMPOSE_FILE="$ROOT/docker-compose.example.yml"
IMAGE=${KEYKU_TEST_IMAGE:-keyku:verify}
TEST_ROOT=$(mktemp -d /tmp/keyku-container-migration.XXXXXX)
PROJECTS=""

compose() {
  project=$1
  data_path=$2
  shift 2
  KEYKU_IMAGE="$IMAGE" \
  KEYKU_DATA_PATH="$data_path" \
  KEYKU_PUBLISHED_PORT=0 \
  ISHIKU_SETUP_SECRET=synthetic-container-migration-secret-123456 \
    docker compose -p "$project" -f "$COMPOSE_FILE" "$@"
}

restore_host_ownership() {
  project=$1
  data_path=$2
  compose "$project" "$data_path" run --rm --no-deps \
    --user 0:0 \
    --entrypoint /bin/sh \
    keyku-init -eu -c \
    "find /data -mindepth 1 -xdev -delete; chmod 0777 /data" \
    >/dev/null 2>&1 || true
}

cleanup() {
  for item in $PROJECTS; do
    project=${item%%:*}
    data_path=${item#*:}
    restore_host_ownership "$project" "$data_path"
    compose "$project" "$data_path" down --remove-orphans >/dev/null 2>&1 || true
  done
  find "$TEST_ROOT" -depth -delete
}

trap cleanup EXIT HUP INT TERM

wait_ready() {
  project=$1
  data_path=$2
  attempt=0
  while [ "$attempt" -lt 30 ]; do
    endpoint=$(compose "$project" "$data_path" port keyku 3000 2>/dev/null || true)
    port=${endpoint##*:}
    if [ -n "$port" ] && curl --fail --silent --show-error "http://127.0.0.1:$port/readyz" >/dev/null 2>&1; then
      printf '%s\n' "$port"
      return 0
    fi
    attempt=$((attempt + 1))
    sleep 1
  done
  compose "$project" "$data_path" ps -a
  compose "$project" "$data_path" logs --no-color
  return 1
}

assert_initializer_and_runtime() {
  project=$1
  data_path=$2
  init_id=$(compose "$project" "$data_path" ps -a -q keyku-init)
  test -n "$init_id"
  test "$(docker inspect --format '{{.State.ExitCode}}' "$init_id")" = "0"
  test "$(docker inspect --format '{{.Config.User}}' "$init_id")" = "0:0"
  test "$(docker inspect --format '{{.HostConfig.NetworkMode}}' "$init_id")" = "none"
  test "$(docker inspect --format '{{.HostConfig.ReadonlyRootfs}}' "$init_id")" = "true"
  test "$(compose "$project" "$data_path" exec -T keyku id -u)" = "10001"
  test "$(compose "$project" "$data_path" exec -T keyku id -g)" = "10001"
  # Substitutions must execute inside the container.
  # shellcheck disable=SC2016
  compose "$project" "$data_path" exec -T keyku sh -eu -c \
    'test -w /data; test "$(stat -c %u /data)" = 10001; test "$(stat -c %a /data)" = 750; test "$(awk "/^CapEff:/ {print \$2}" /proc/self/status)" = 0000000000000000; test "$(awk "/^NoNewPrivs:/ {print \$2}" /proc/self/status)" = 1'
}

assert_init_security_config() {
  project=$1
  data_path=$2
  # Awk must execute inside the container.
  # shellcheck disable=SC2016
  init_security=$(compose "$project" "$data_path" run --rm --no-deps --entrypoint /bin/sh keyku-init -c \
    'awk "/^CapEff:|^NoNewPrivs:/ {print \$2}" /proc/self/status' | tr '\n' ' ')
  test "$init_security" = "000000000000000b 1 "
}

fresh_data="$TEST_ROOT/fresh"
install -d -m 0755 "$fresh_data"
fresh_project="keyku-fresh-$$"
PROJECTS="$PROJECTS $fresh_project:$fresh_data"
assert_init_security_config "$fresh_project" "$fresh_data"
compose "$fresh_project" "$fresh_data" up -d
wait_ready "$fresh_project" "$fresh_data" >/dev/null
assert_initializer_and_runtime "$fresh_project" "$fresh_data"
compose "$fresh_project" "$fresh_data" exec -T keyku sh -eu -c 'test -s /data/session-secret.txt'
restore_host_ownership "$fresh_project" "$fresh_data"
compose "$fresh_project" "$fresh_data" down --remove-orphans >/dev/null
PROJECTS=""

legacy_data="$TEST_ROOT/legacy"
install -d -m 0700 "$legacy_data"
python3 - "$legacy_data" <<'PY'
import base64
import hashlib
import json
import os
import sys
from pathlib import Path

data = Path(sys.argv[1])
salt = "synthetic-legacy-salt"
password = "synthetic-legacy-password-123456"
digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), 310000, dklen=32)
encoded = base64.urlsafe_b64encode(digest).rstrip(b"=").decode()
users = {
    "users": [{
        "id": "synthetic-legacy-admin",
        "username": "legacy-admin",
        "displayName": "Synthetic Legacy Admin",
        "role": "admin",
        "status": "approved",
        "passwordHash": encoded,
        "salt": salt,
        "iterations": 310000,
    }]
}
(data / "users.json").write_text(json.dumps(users), encoding="utf-8")
(data / "setup-state.json").write_text(json.dumps({"setupCompleted": True}), encoding="utf-8")
(data / "session-secret.txt").write_text("synthetic-legacy-session-secret-1234567890\n", encoding="utf-8")
(data / "keys.csv").write_text(
    "Game,Key,RedeemedAt,addedAt,RedeemedBy,RedeemedByName\n"
    "Synthetic Legacy Game,AAAA-BBBB-CCCC,,2026-01-01T00:00:00Z,,\n",
    encoding="utf-8",
)
for path in data.iterdir():
    os.chmod(path, 0o600)
PY

legacy_project="keyku-legacy-$$"
PROJECTS="$PROJECTS $legacy_project:$legacy_data"
compose "$legacy_project" "$legacy_data" up -d
legacy_port=$(wait_ready "$legacy_project" "$legacy_data")
assert_initializer_and_runtime "$legacy_project" "$legacy_data"
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  --data '{"username":"legacy-admin","password":"synthetic-legacy-password-123456"}' \
  "http://127.0.0.1:$legacy_port/api/auth/login" >/dev/null
compose "$legacy_project" "$legacy_data" exec -T keyku python - <<'PY'
import json
from pathlib import Path

users = json.loads(Path("/data/users.json").read_text(encoding="utf-8"))["users"]
assert users[0]["passwordAlgorithm"] == "argon2id"
assert users[0]["passwordHash"].startswith("$argon2id$")
assert "salt" not in users[0]
assert "iterations" not in users[0]
assert "Synthetic Legacy Game" in Path("/data/keys.csv").read_text(encoding="utf-8")
PY
compose "$legacy_project" "$legacy_data" restart keyku >/dev/null
wait_ready "$legacy_project" "$legacy_data" >/dev/null
compose "$legacy_project" "$legacy_data" exec -T keyku grep -q 'Synthetic Legacy Game' /data/keys.csv

# Exercise the documented full-directory backup and restore path with the same
# non-root UID that owns the persistent data. The copy containers have no
# network, capabilities, writable root filesystem, or privilege escalation.
compose "$legacy_project" "$legacy_data" stop keyku >/dev/null
backup_data="$TEST_ROOT/backup"
restore_data="$TEST_ROOT/restore"
install -d -m 0777 "$backup_data" "$restore_data"
backup_cleanup_project="keyku-backup-cleanup-$$"
PROJECTS="$PROJECTS $backup_cleanup_project:$backup_data"
docker run --rm \
  --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --user 10001:10001 \
  -v "$legacy_data:/source:ro,z" \
  -v "$backup_data:/destination:rw,z" \
  "$IMAGE" \
  python -c 'import shutil; shutil.copytree("/source", "/destination/data", copy_function=shutil.copy2)'
docker run --rm \
  --network none \
  --read-only \
  --cap-drop ALL \
  --security-opt no-new-privileges:true \
  --user 10001:10001 \
  -v "$backup_data/data:/source:ro,z" \
  -v "$restore_data:/destination:rw,z" \
  "$IMAGE" \
  python -c 'import pathlib, shutil; source = pathlib.Path("/source"); destination = pathlib.Path("/destination"); [(shutil.copytree(item, destination / item.name, copy_function=shutil.copy2) if item.is_dir() else shutil.copy2(item, destination / item.name)) for item in source.iterdir()]'
compose "$legacy_project" "$legacy_data" down --remove-orphans >/dev/null

restore_project="keyku-restore-$$"
PROJECTS="$PROJECTS $restore_project:$restore_data"
compose "$restore_project" "$restore_data" up -d
restore_port=$(wait_ready "$restore_project" "$restore_data")
assert_initializer_and_runtime "$restore_project" "$restore_data"
curl --fail --silent --show-error \
  -H 'Content-Type: application/json' \
  --data '{"username":"legacy-admin","password":"synthetic-legacy-password-123456"}' \
  "http://127.0.0.1:$restore_port/api/auth/login" >/dev/null
compose "$restore_project" "$restore_data" exec -T keyku grep -q 'Synthetic Legacy Game' /data/keys.csv

printf '%s\n' "Keyku container migration, persistence, backup, and restore checks passed."
