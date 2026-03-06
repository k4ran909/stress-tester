# 🔥 AegisShield Stress Tester v4.0 (ULTIMATE)

A self-contained, zero-dependency stress testing toolkit with **46 attack methods**. Supports standalone mode and distributed controller/worker architecture.

## Architecture

```
┌─ Standalone Mode ─────────────────────────────────┐
│  python start.py <method> <target> <threads> <dur> │
│  python start.py TOOLS                             │
└────────────────────────────────────────────────────┘

┌─ Distributed Mode ────────────────────────────────┐
│  Controller (Your PC)       Worker 1 (Remote)     │
│  python controller.py  ◄──► python worker.py      │
│  Port 7777                  --master <IP>:7777    │
│                             Worker 2 (Remote)     │
│                        ◄──► python worker.py      │
│                             --master <IP>:7777    │
└────────────────────────────────────────────────────┘
```

## Quick Start

### Standalone Mode (Single Machine)
```bash
# Layer 4 attack
python start.py UDP 1.2.3.4:80 100 60
python start.py VSE 1.2.3.4:27015 50 120
python start.py MCBOT 1.2.3.4:25565 30 60

# Layer 7 attack
python start.py GET https://target.com 200 60
python start.py SLOW https://target.com 100 120
python start.py POST https://target.com 150 60

# Recon tools console
python start.py TOOLS

# Help
python start.py HELP
```

### Distributed Mode (Multiple Machines)

**1. Start Controller (Main PC):**
```bash
python controller.py --port 7777
```

**2. Start Workers (Each Remote Device):**
```bash
python worker.py --master <CONTROLLER_IP>:7777
```

**3. Controller Commands:**
```bash
# L4 attack
aegis-stress> attack 1.2.3.4:80 UDP 100 60 100

# L7 attack
aegis-stress> attack https://target.com GET 200 60

# Gaming protocols
aegis-stress> attack 1.2.3.4:27015 VSE 50 120
aegis-stress> attack 1.2.3.4:25565 MCBOT 30 60

# Control
aegis-stress> stop       # stop all workers
aegis-stress> status     # show connected workers
aegis-stress> methods    # list all methods
aegis-stress> exit       # shutdown
```

## All 46 Methods

### Layer 4 (21 Methods)

| Method | Type | Description |
|--------|------|-------------|
| `UDP` | Volumetric | Raw UDP packet flood |
| `TCP` | Volumetric | TCP connection + data flood |
| `SYN` | Volumetric | TCP SYN flood (non-blocking) |
| `ICMP` | Volumetric | ICMP echo flood (requires admin) |
| `OVH-UDP` | Volumetric | UDP with HTTP headers to bypass OVH/WAFs |
| `CPS` | Connection | Rapid open/close connections |
| `CONNECTION` | Connection | Hold TCP connections alive |
| `VSE` | Gaming | Valve Source Engine query flood |
| `TS3` | Gaming | TeamSpeak 3 status ping flood |
| `FIVEM` | Gaming | FiveM getinfo flood |
| `FIVEM-TOKEN` | Gaming | FiveM getstatus flood |
| `MCBOT` | Gaming | Minecraft fake player joins |
| `MINECRAFT` | Gaming | Minecraft status ping flood |
| `MCPE` | Gaming | Minecraft PE status ping |
| `MEM` | Amplification | Memcached amplification |
| `NTP` | Amplification | NTP monlist amplification |
| `DNS` | Amplification | DNS ANY query amplification |
| `CHAR` | Amplification | Chargen amplification |
| `CLDAP` | Amplification | CLDAP amplification |
| `ARD` | Amplification | Apple Remote Desktop amp |
| `RDP` | Amplification | Remote Desktop Protocol amp |

### Layer 7 (25 Methods)

| Method | Type | Description |
|--------|------|-------------|
| `GET` | Basic | HTTP GET flood |
| `POST` | Basic | HTTP POST with JSON body |
| `HEAD` | Basic | HTTP HEAD flood |
| `PPS` | Basic | Minimal-header GET for max PPS |
| `EVEN` | Basic | GET + read response |
| `NULL` | Basic | Null user-agent GET |
| `COOKIE` | Basic | GET with random cookies |
| `CFB` | Advanced | Cloudflare bypass headers |
| `CFBUAM` | Advanced | CF Under Attack Mode bypass |
| `BYPASS` | Advanced | Generic WAF bypass |
| `OVH` | Advanced | Multi-request per connection |
| `DYN` | Advanced | Dynamic subdomain rotation |
| `GSB` | Advanced | HEAD with query strings |
| `RHEX` | Advanced | Random hex path flood |
| `STOMP` | Advanced | Host header manipulation |
| `DGB` | Advanced | GET bypass |
| `AVB` | Advanced | Slow GET with delays |
| `STRESS` | Resource | Heavy JSON POST |
| `SLOW` | Resource | Slowloris connection hold |
| `APACHE` | Resource | Apache Range header exploit |
| `XMLRPC` | Resource | WordPress XML-RPC pingback |
| `BOT` | Resource | Bot-like crawling |
| `BOMB` | Resource | Repeated GET per connection |
| `DOWNLOADER` | Resource | GET + full body download |
| `KILLER` | Resource | 10x GET per connection |

## Tools Console

Run `python start.py TOOLS` for:

| Tool | Description |
|------|-------------|
| `CFIP <domain>` | Find real IP behind Cloudflare |
| `DNS <domain>` | Show DNS records (A, MX, TXT, NS, etc.) |
| `TSSRV <domain>` | TeamSpeak SRV resolver |
| `PING <host>` | Ping a server |
| `CHECK <url>` | Check website status |
| `DSTAT` | Live network I/O stats |

## File Structure

```
stress-tester/
├── start.py        # Standalone tool (all 46 methods + tools)
├── controller.py   # Distributed controller (master)
├── worker.py       # Distributed worker (connects to controller)
├── config.json     # Configuration
└── README.md       # This file
```

## Requirements

- **Python 3.8+**
- **Zero external dependencies** (stdlib only)
- ICMP method requires admin/root privileges

## ⚠️ Legal Notice

This tool is for **testing your own servers only**. Unauthorized use against servers you don't own is illegal.
