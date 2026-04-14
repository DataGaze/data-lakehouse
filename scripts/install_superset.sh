#!/usr/bin/env bash
# install_superset.sh — Install Apache Superset native on Debian 13 (LXC 205)
#
# Usage:
#   PG_GOLD_PASS=xxx bash install_superset.sh
#   PG_GOLD_PASS=xxx ADMIN_PASS=mypass bash install_superset.sh
#
# Idempotent: safe to re-run. Skips steps already completed.

set -euo pipefail

# ── Colors & Logging ─────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'; NC='\033[0m'
log()  { echo -e "${GREEN}[$(date +%H:%M:%S)]${NC} $*"; }
warn() { echo -e "${YELLOW}[$(date +%H:%M:%S)] WARN:${NC} $*"; }
err()  { echo -e "${RED}[$(date +%H:%M:%S)] ERROR:${NC} $*" >&2; }

# ── Configuration (override via env) ─────────────────────────────
PYTHON_VERSION="${PYTHON_VERSION:-3.11.12}"
PYTHON_MAJOR="3.11"
PYTHON_PREFIX="${PYTHON_PREFIX:-/opt/python311}"
INSTALL_DIR="${INSTALL_DIR:-/opt/superset}"

# Metadata DB (local PostgreSQL on this host)
META_DB_NAME="${META_DB_NAME:-superset_meta}"
META_DB_USER="${META_DB_USER:-superset}"
META_DB_PASS="${META_DB_PASS:-$(openssl rand -hex 16)}"

# Superset admin
ADMIN_USER="${ADMIN_USER:-admin}"
ADMIN_PASS="${ADMIN_PASS:-$(openssl rand -hex 8)}"
ADMIN_EMAIL="${ADMIN_EMAIL:-admin@datagaze.local}"

# PG Gold (data source)
PG_GOLD_HOST="${PG_GOLD_HOST:-192.168.0.113}"
PG_GOLD_PORT="${PG_GOLD_PORT:-5432}"
PG_GOLD_DB="${PG_GOLD_DB:-stock_market}"
PG_GOLD_USER="${PG_GOLD_USER:-stock}"
PG_GOLD_PASS="${PG_GOLD_PASS:-}"

# Secret key
SECRET_KEY="${SECRET_KEY:-$(openssl rand -hex 32)}"

# ── Step 1: System Dependencies ──────────────────────────────────
install_system_deps() {
    log "Step 1/9: Installing system dependencies..."
    export DEBIAN_FRONTEND=noninteractive
    apt-get update -qq
    apt-get install -y -qq \
        build-essential pkg-config \
        libssl-dev libffi-dev libpq-dev \
        zlib1g-dev libbz2-dev libreadline-dev libsqlite3-dev \
        liblzma-dev libncurses5-dev libncursesw5-dev \
        libxml2-dev libxslt1-dev libsasl2-dev libldap2-dev \
        wget curl git \
        postgresql postgresql-contrib \
        redis-server
    log "System dependencies installed."
}

# ── Step 2: Build Python 3.12 ────────────────────────────────────
build_python() {
    if [[ -x "${PYTHON_PREFIX}/bin/python${PYTHON_MAJOR}" ]]; then
        log "Step 2/9: Python ${PYTHON_MAJOR} already at ${PYTHON_PREFIX} — skipping."
        return
    fi

    log "Step 2/9: Building Python ${PYTHON_VERSION} from source (~5 min)..."
    local src_dir="/tmp/python-build-$$"
    mkdir -p "$src_dir"
    cd "$src_dir"

    wget -q "https://www.python.org/ftp/python/${PYTHON_VERSION}/Python-${PYTHON_VERSION}.tgz"
    tar xzf "Python-${PYTHON_VERSION}.tgz"
    cd "Python-${PYTHON_VERSION}"

    ./configure \
        --prefix="${PYTHON_PREFIX}" \
        --enable-shared \
        --with-system-ffi \
        --with-ensurepip=install \
        LDFLAGS="-Wl,-rpath,${PYTHON_PREFIX}/lib" \
        > /tmp/python-configure.log 2>&1

    make -j"$(nproc)" > /tmp/python-make.log 2>&1
    make altinstall > /tmp/python-install.log 2>&1

    cd / && rm -rf "$src_dir"
    log "Python ${PYTHON_VERSION} installed at ${PYTHON_PREFIX}/bin/python${PYTHON_MAJOR}"
}

# ── Step 3: PostgreSQL metadata DB ────────────────────────────────
setup_metadata_db() {
    log "Step 3/9: Setting up metadata database..."
    systemctl enable --now postgresql

    # Create user (idempotent) — use su since sudo may not exist in LXC
    su - postgres -c "psql -tc \"SELECT 1 FROM pg_roles WHERE rolname='${META_DB_USER}'\"" \
        | grep -q 1 \
        || su - postgres -c "psql -c \"CREATE USER ${META_DB_USER} WITH PASSWORD '${META_DB_PASS}';\""

    # Create database (idempotent)
    su - postgres -c "psql -tc \"SELECT 1 FROM pg_database WHERE datname='${META_DB_NAME}'\"" \
        | grep -q 1 \
        || su - postgres -c "psql -c \"CREATE DATABASE ${META_DB_NAME} OWNER ${META_DB_USER};\""

    log "Metadata DB ready: ${META_DB_NAME}"
}

# ── Step 4: Redis ─────────────────────────────────────────────────
setup_redis() {
    log "Step 4/9: Starting Redis..."
    systemctl enable --now redis-server
    log "Redis ready."
}

# ── Step 5: Superset venv + pip install ───────────────────────────
install_superset() {
    log "Step 5/9: Installing Apache Superset..."
    mkdir -p "${INSTALL_DIR}"

    if [[ ! -d "${INSTALL_DIR}/venv" ]]; then
        "${PYTHON_PREFIX}/bin/python${PYTHON_MAJOR}" -m venv "${INSTALL_DIR}/venv"
    fi

    local pip="${INSTALL_DIR}/venv/bin/pip"
    # Pin setuptools<75 — Superset 4.x uses pkg_resources (removed in setuptools 78+)
    $pip install --upgrade pip "setuptools<75" wheel > /tmp/superset-pip-upgrade.log 2>&1
    $pip install \
        "apache-superset>=4.0,<5.0" \
        psycopg2-binary \
        redis \
        gevent \
        pillow \
        flask-cors \
        > /tmp/superset-pip-install.log 2>&1

    local version
    version=$("${INSTALL_DIR}/venv/bin/superset" version 2>/dev/null || echo "unknown")
    log "Superset ${version} installed in ${INSTALL_DIR}/venv"
}

# ── Step 6: Config ────────────────────────────────────────────────
write_config() {
    log "Step 6/9: Writing Superset config..."

    cat > "${INSTALL_DIR}/superset_config.py" << 'PYEOF'
import os

# ── Security ──
SECRET_KEY = os.environ.get("SUPERSET_SECRET_KEY", "PLACEHOLDER_SECRET_KEY")
CSRF_ENABLED = True

# ── Metadata DB ──
SQLALCHEMY_DATABASE_URI = os.environ.get(
    "SUPERSET_META_URI",
    "PLACEHOLDER_META_URI"
)

# ── Cache (Redis) ──
CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 300,
    "CACHE_KEY_PREFIX": "superset_",
    "CACHE_REDIS_URL": "redis://localhost:6379/0",
}
DATA_CACHE_CONFIG = {
    "CACHE_TYPE": "RedisCache",
    "CACHE_DEFAULT_TIMEOUT": 600,
    "CACHE_KEY_PREFIX": "superset_data_",
    "CACHE_REDIS_URL": "redis://localhost:6379/1",
}

# ── Celery (async queries for large ticks table) ──
class CeleryConfig:
    broker_url = "redis://localhost:6379/2"
    result_backend = "redis://localhost:6379/3"
    worker_prefetch_multiplier = 1
    task_acks_late = True

CELERY_CONFIG = CeleryConfig

# ── Web Server ──
SUPERSET_WEBSERVER_PORT = 8088
SUPERSET_WEBSERVER_TIMEOUT = 120
ENABLE_CORS = True
CORS_OPTIONS = {
    "supports_credentials": True,
    "allow_headers": ["*"],
    "resources": ["*"],
    "origins": ["*"],
}

# ── Features ──
FEATURE_FLAGS = {
    "ENABLE_TEMPLATE_PROCESSING": True,
    "DASHBOARD_NATIVE_FILTERS": True,
    "DASHBOARD_CROSS_FILTERS": True,
    "EMBEDDED_SUPERSET": True,
}

# ── Row Limits ──
ROW_LIMIT = 50000
SQL_MAX_ROW = 100000
VIZ_ROW_LIMIT = 10000

# ── Languages ──
BABEL_DEFAULT_LOCALE = "en"
LANGUAGES = {
    "en": {"flag": "us", "name": "English"},
    "vi": {"flag": "vn", "name": "Vietnamese"},
}

# ── API ──
FAB_API_MAX_PAGE_SIZE = 100
WTF_CSRF_ENABLED = True
WTF_CSRF_EXEMPT_LIST = [
    "superset.views.core.log",
    "superset.charts.api",
    "superset.dashboards.api",
]
PYEOF

    # Replace placeholders with actual values (avoid secrets in heredoc)
    sed -i "s|PLACEHOLDER_SECRET_KEY|${SECRET_KEY}|" "${INSTALL_DIR}/superset_config.py"
    sed -i "s|PLACEHOLDER_META_URI|postgresql://${META_DB_USER}:${META_DB_PASS}@localhost:5432/${META_DB_NAME}|" \
        "${INSTALL_DIR}/superset_config.py"

    log "Config written to ${INSTALL_DIR}/superset_config.py"
}

# ── Step 7: Initialize Superset ───────────────────────────────────
init_superset() {
    log "Step 7/9: Initializing Superset (db upgrade + admin)..."

    export SUPERSET_CONFIG_PATH="${INSTALL_DIR}/superset_config.py"
    export FLASK_APP="superset"
    local superset="${INSTALL_DIR}/venv/bin/superset"

    $superset db upgrade > /tmp/superset-db-upgrade.log 2>&1

    # Create admin (ignore error if already exists)
    $superset fab create-admin \
        --username "${ADMIN_USER}" \
        --firstname "Admin" \
        --lastname "DataGaze" \
        --email "${ADMIN_EMAIL}" \
        --password "${ADMIN_PASS}" \
        > /tmp/superset-create-admin.log 2>&1 || true

    $superset init > /tmp/superset-init.log 2>&1

    log "Superset initialized. Admin: ${ADMIN_USER}"
}

# ── Step 8: Systemd Services ──────────────────────────────────────
create_services() {
    log "Step 8/9: Creating systemd services..."

    # Create superset system user (idempotent)
    id -u superset &>/dev/null || useradd -r -s /bin/false -d "${INSTALL_DIR}" superset
    chown -R superset:superset "${INSTALL_DIR}"

    # --- superset-web.service (Gunicorn) ---
    cat > /etc/systemd/system/superset-web.service << EOF
[Unit]
Description=Apache Superset Web (Gunicorn)
After=postgresql.service redis-server.service
Wants=postgresql.service redis-server.service

[Service]
User=superset
Group=superset
Environment=SUPERSET_CONFIG_PATH=${INSTALL_DIR}/superset_config.py
Environment=FLASK_APP=superset
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/gunicorn \
    --bind 0.0.0.0:8088 \
    --workers 2 \
    --worker-class gthread \
    --threads 4 \
    --timeout 120 \
    --limit-request-line 0 \
    --limit-request-field_size 0 \
    "superset.app:create_app()"
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    # --- superset-worker.service (Celery) ---
    cat > /etc/systemd/system/superset-worker.service << EOF
[Unit]
Description=Apache Superset Celery Worker
After=redis-server.service
Wants=redis-server.service

[Service]
User=superset
Group=superset
Environment=SUPERSET_CONFIG_PATH=${INSTALL_DIR}/superset_config.py
Environment=FLASK_APP=superset
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/venv/bin/celery \
    --app=superset.tasks.celery_app:app worker \
    --pool=prefork \
    --concurrency=2 \
    -Ofair \
    --loglevel=INFO
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable superset-web superset-worker
    systemctl start superset-web superset-worker

    # Wait for web to be healthy
    log "Waiting for Superset to start..."
    for i in $(seq 1 30); do
        if curl -sf -o /dev/null http://localhost:8088/health 2>/dev/null; then
            log "Superset is healthy!"
            return
        fi
        sleep 2
    done
    warn "Superset not responding after 60s. Check: journalctl -u superset-web"
}

# ── Step 9: Add PG Gold Data Source ───────────────────────────────
add_pg_gold() {
    if [[ -z "${PG_GOLD_PASS}" ]]; then
        warn "Step 9/9: PG_GOLD_PASS not set — skipping auto-add."
        warn "Add PG Gold manually via Superset UI."
        return
    fi

    log "Step 9/9: Adding PG Gold as data source..."

    # Login to get JWT token
    local login_resp
    login_resp=$(curl -sf -X POST http://localhost:8088/api/v1/security/login \
        -H "Content-Type: application/json" \
        -d "{\"username\":\"${ADMIN_USER}\",\"password\":\"${ADMIN_PASS}\",\"provider\":\"db\"}" \
        2>/dev/null || echo "{}")

    local token
    token=$(echo "$login_resp" | "${INSTALL_DIR}/venv/bin/python" -c \
        "import sys,json; print(json.load(sys.stdin).get('access_token',''))" 2>/dev/null || echo "")

    if [[ -z "$token" ]]; then
        warn "Could not get API token — add PG Gold manually."
        return
    fi

    # Get CSRF token
    local csrf
    csrf=$(curl -sf http://localhost:8088/api/v1/security/csrf_token/ \
        -H "Authorization: Bearer ${token}" \
        2>/dev/null \
        | "${INSTALL_DIR}/venv/bin/python" -c \
            "import sys,json; print(json.load(sys.stdin).get('result',''))" 2>/dev/null || echo "")

    # Create database connection
    local resp
    resp=$(curl -sf -X POST http://localhost:8088/api/v1/database/ \
        -H "Authorization: Bearer ${token}" \
        -H "Content-Type: application/json" \
        -H "X-CSRFToken: ${csrf}" \
        -H "Referer: http://localhost:8088/" \
        -d "{
            \"database_name\": \"PG Gold - Stock Market\",
            \"engine\": \"postgresql\",
            \"sqlalchemy_uri\": \"postgresql://${PG_GOLD_USER}:${PG_GOLD_PASS}@${PG_GOLD_HOST}:${PG_GOLD_PORT}/${PG_GOLD_DB}\",
            \"expose_in_sqllab\": true,
            \"allow_ctas\": false,
            \"allow_cvas\": false,
            \"allow_dml\": false,
            \"allow_run_async\": true,
            \"extra\": \"{\\\"allows_virtual_table_explore\\\": true}\"
        }" 2>/dev/null || echo "{}")

    if echo "$resp" | grep -q '"id"'; then
        log "PG Gold data source added successfully."
    else
        warn "PG Gold add response: ${resp}"
        warn "May need manual configuration via UI."
    fi
}

# ── Save Credentials ──────────────────────────────────────────────
save_credentials() {
    cat > "${INSTALL_DIR}/.credentials" << EOF
# Superset Credentials — generated $(date -I)
# Keep this file secure (chmod 600)
ADMIN_USER=${ADMIN_USER}
ADMIN_PASS=${ADMIN_PASS}
META_DB_USER=${META_DB_USER}
META_DB_PASS=${META_DB_PASS}
SECRET_KEY=${SECRET_KEY}
SUPERSET_URL=http://$(hostname -I | awk '{print $1}'):8088
EOF
    chmod 600 "${INSTALL_DIR}/.credentials"
}

# ── Main ──────────────────────────────────────────────────────────
main() {
    if [[ $EUID -ne 0 ]]; then
        err "Must run as root"
        exit 1
    fi

    local host_ip
    host_ip=$(hostname -I | awk '{print $1}')

    log "════════════════════════════════════════════════════"
    log " Apache Superset — Native Install"
    log " Host: $(hostname) (${host_ip})"
    log " OS:   $(grep PRETTY_NAME /etc/os-release | cut -d= -f2 | tr -d '"')"
    log "════════════════════════════════════════════════════"

    install_system_deps
    build_python
    setup_metadata_db
    setup_redis
    install_superset
    write_config
    init_superset
    create_services
    add_pg_gold
    save_credentials

    log ""
    log "════════════════════════════════════════════════════"
    log " ✓ Installation Complete!"
    log "════════════════════════════════════════════════════"
    log ""
    log "  URL:       http://${host_ip}:8088"
    log "  Admin:     ${ADMIN_USER} / ${ADMIN_PASS}"
    log "  Config:    ${INSTALL_DIR}/superset_config.py"
    log "  Creds:     ${INSTALL_DIR}/.credentials"
    log "  Services:  superset-web, superset-worker"
    log ""
    log "  Useful commands:"
    log "    systemctl status superset-web"
    log "    journalctl -u superset-web -f"
    log "    journalctl -u superset-worker -f"
    log ""
}

main "$@"
