# 🔥 Stress Tester — Distributed Load Testing Tool

A distributed stress testing tool to test your server's resilience. Supports **UDP, TCP, HTTP, HTTPS** flood methods.

## Architecture

```
┌──────────────┐          ┌──────────┐
│  Controller  │◄────────►│ Worker 1 │
│  (Your PC)   │          └──────────┘
│              │          ┌──────────┐
│  Port 7777   │◄────────►│ Worker 2 │
│              │          └──────────┘
│  CLI prompt  │          ┌──────────┐
│              │◄────────►│ Worker N │
└──────────────┘          └──────────┘
```

## Quick Start

### 1. Controller (Main PC)
```bash
python3 controller.py --port 7777
```

### 2. Workers (Each Ubuntu Device)
```bash
python3 worker.py --master <CONTROLLER_IP>:7777
```

### 3. Commands
```bash
# syntax: attack <IP> <PORT> <METHOD> <SIZE|RAND> <DURATION> [POWER%]

# UDP flood (Max power, 65KB packets for 60 seconds)
aegis-stress> attack 1.2.3.4 12345 udp 65507 60 100

# UDP flood (Low power 10%, random packet sizes up to 65KB)
aegis-stress> attack 1.2.3.4 12345 udp RAND 60 10

# TCP flood (1KB per connection for 30s)
aegis-stress> attack 1.2.3.4 80 tcp 1024 30

# HTTP GET flood (30 seconds)
aegis-stress> attack 1.2.3.4 80 http 0 30

# Slowloris attack (Hold connections open, 100% power)
aegis-stress> attack 1.2.3.4 80 slow 0 120 100

# Stop all workers
aegis-stress> stop

# Check connected workers
aegis-stress> status
```

## Methods

| Method | Description | Best For |
|--------|-------------|----------|
| `udp` | Raw UDP packet flood | Bandwidth stress test |
| `tcp` | TCP connection flood | Connection table stress |
| `http` | HTTP GET request flood | Web server stress |
| `https` | HTTPS GET request flood | TLS + web stress |
| `slow` | Slowloris connection hold | Proxy / Web server exhaustion |

## Requirements

- Python 3.8+
- No external dependencies (stdlib only)

## ⚠️ Legal Notice

This tool is for **testing your own servers only**. Unauthorized use against servers you don't own is illegal.
