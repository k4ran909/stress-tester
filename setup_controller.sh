#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  AegisShield Controller — One-Line Setup Script
#  Run: curl -sL <raw_url>/setup_controller.sh | bash
# ═══════════════════════════════════════════════════════════════
set -e

PORT=${1:-7777}
INSTALL_DIR="/opt/aegis"
SERVICE_NAME="aegis-controller"

echo ""
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║  AegisShield Controller — Auto Setup              ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo ""

# ── 1. Install Python3 if missing ──────────────────────────────
if ! command -v python3 &>/dev/null; then
    echo "  [1/6] Installing Python3..."
    apt-get update -qq && apt-get install -y -qq python3 python3-pip >/dev/null 2>&1 || \
    yum install -y python3 >/dev/null 2>&1 || \
    apk add python3 >/dev/null 2>&1
else
    echo "  [1/6] Python3 ✅ ($(python3 --version 2>&1))"
fi

# ── 2. Install screen if missing ──────────────────────────────
if ! command -v screen &>/dev/null; then
    echo "  [2/6] Installing screen..."
    apt-get install -y -qq screen >/dev/null 2>&1 || \
    yum install -y screen >/dev/null 2>&1 || \
    apk add screen >/dev/null 2>&1
else
    echo "  [2/6] screen ✅"
fi

# ── 3. Create install directory ───────────────────────────────
echo "  [3/6] Setting up ${INSTALL_DIR}..."
mkdir -p "$INSTALL_DIR"

# ── 4. Download controller.py ─────────────────────────────────
echo "  [4/6] Downloading controller.py..."
curl -sL https://raw.githubusercontent.com/k4ran909/stress-tester/master/controller.py -o "${INSTALL_DIR}/controller.py"
chmod +x "${INSTALL_DIR}/controller.py"

# ── 5. Open firewall port ────────────────────────────────────
echo "  [5/6] Opening port ${PORT}..."
# Try ufw
if command -v ufw &>/dev/null; then
    ufw allow ${PORT}/tcp >/dev/null 2>&1 || true
fi
# Try iptables
if command -v iptables &>/dev/null; then
    iptables -C INPUT -p tcp --dport ${PORT} -j ACCEPT 2>/dev/null || \
    iptables -A INPUT -p tcp --dport ${PORT} -j ACCEPT 2>/dev/null || true
fi
# Try firewall-cmd (CentOS/RHEL)
if command -v firewall-cmd &>/dev/null; then
    firewall-cmd --permanent --add-port=${PORT}/tcp >/dev/null 2>&1 || true
    firewall-cmd --reload >/dev/null 2>&1 || true
fi

# ── 6. Kill old instance & start in screen ────────────────────
echo "  [6/6] Starting controller on port ${PORT}..."

# Kill any existing aegis screen
screen -ls | grep -q "aegis" && screen -X -S aegis quit 2>/dev/null || true

# Start in detached screen
screen -dmS aegis python3 "${INSTALL_DIR}/controller.py" --port ${PORT}

# Wait a moment and verify
sleep 2
if screen -ls | grep -q "aegis"; then
    PUBLIC_IP=$(curl -s ifconfig.me 2>/dev/null || curl -s icanhazip.com 2>/dev/null || echo "<YOUR_IP>")
    echo ""
    echo "  ╔═══════════════════════════════════════════════════╗"
    echo "  ║  ✅ Controller is RUNNING (24/7)                  ║"
    echo "  ╠═══════════════════════════════════════════════════╣"
    echo "  ║  Port:     ${PORT}                                "
    echo "  ║  Public IP: ${PUBLIC_IP}                          "
    echo "  ╚═══════════════════════════════════════════════════╝"
    echo ""
    echo "  📋 Worker install command (run on each worker):"
    echo ""
    echo "  curl -sL https://raw.githubusercontent.com/k4ran909/stress-tester/master/setup_worker.sh | bash -s ${PUBLIC_IP} ${PORT}"
    echo ""
    echo "  🖥  To access controller prompt:"
    echo "     screen -r aegis"
    echo ""
    echo "  ⌨  To detach (keep running):"
    echo "     Press Ctrl+A then D"
    echo ""
    echo "  🔄 To restart controller:"
    echo "     screen -X -S aegis quit; screen -dmS aegis python3 ${INSTALL_DIR}/controller.py --port ${PORT}"
    echo ""
else
    echo "  ❌ Failed to start. Check: python3 ${INSTALL_DIR}/controller.py --port ${PORT}"
    exit 1
fi
