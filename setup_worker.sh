#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  AegisShield Worker — One-Line Setup Script
#  Run: curl -sL <raw_url>/setup_worker.sh | bash -s <CONTROLLER_IP> <PORT>
# ═══════════════════════════════════════════════════════════════
set -e

CONTROLLER_IP=${1:-"159.65.32.13"}
CONTROLLER_PORT=${2:-7777}
INSTALL_DIR="/opt/aegis"
SERVICE_NAME="aegis-worker"

echo ""
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║  AegisShield Worker — Auto Setup                  ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo ""

# ── 1. Install Python3 if missing ──────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "  [1/5] Installing Python3..."
    apt-get update -qq && apt-get install -y -qq python3 >/dev/null 2>&1 || \
    yum install -y python3 >/dev/null 2>&1 || \
    apk add python3 >/dev/null 2>&1
else
    echo "  [1/5] Python3 ✅ ($(python3 --version 2>&1))"
fi

# ── 2. Create install directory ───────────────────────────────
echo "  [2/5] Setting up ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"

# ── 3. Download worker.py ────────────────────────────────────
echo "  [3/5] Downloading worker.py..."
curl -sL https://raw.githubusercontent.com/k4ran909/stress-tester/master/worker.py -o "${INSTALL_DIR}/worker.py"
chmod +x "${INSTALL_DIR}/worker.py"

# ── 4. Create systemd service (auto-restart, runs forever) ────
echo "  [4/5] Creating systemd service..."
cat > /etc/systemd/system/${SERVICE_NAME}.service << EOF
[Unit]
Description=AegisShield Stress Worker
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
ExecStart=/usr/bin/python3 ${INSTALL_DIR}/worker.py --master ${CONTROLLER_IP}:${CONTROLLER_PORT}
Restart=always
RestartSec=5
StartLimitInterval=0
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=multi-user.target
EOF

# ── 5. Enable and start ──────────────────────────────────────
echo "  [5/5] Starting worker service..."
systemctl daemon-reload
systemctl enable ${SERVICE_NAME} >/dev/null 2>&1
systemctl restart ${SERVICE_NAME}

# Wait and verify
sleep 3
if systemctl is-active --quiet ${SERVICE_NAME}; then
    echo ""
    echo "  ╔═══════════════════════════════════════════════════╗"
    echo "  ║  ✅ Worker is RUNNING (24/7, auto-restart)        ║"
    echo "  ╠═══════════════════════════════════════════════════╣"
    echo "  ║  Controller: ${CONTROLLER_IP}:${CONTROLLER_PORT}  "
    echo "  ║  Service:    ${SERVICE_NAME}                      "
    echo "  ║  Auto-start: ON (survives reboot)                 ║"
    echo "  ║  Auto-restart: ON (restarts on crash)             ║"
    echo "  ╚═══════════════════════════════════════════════════╝"
    echo ""
    echo "  📋 Useful commands:"
    echo "     systemctl status ${SERVICE_NAME}     # check status"
    echo "     journalctl -u ${SERVICE_NAME} -f     # live logs"
    echo "     systemctl restart ${SERVICE_NAME}    # restart"
    echo "     systemctl stop ${SERVICE_NAME}       # stop"
    echo ""
else
    echo "  ❌ Service failed. Checking logs..."
    journalctl -u ${SERVICE_NAME} -n 20 --no-pager
    echo ""
    echo "  Try manual run: python3 ${INSTALL_DIR}/worker.py --master ${CONTROLLER_IP}:${CONTROLLER_PORT}"
    exit 1
fi
