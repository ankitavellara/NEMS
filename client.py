import hashlib
import hmac
import json
import re
import socket
import subprocess
import time

import psutil

CRITICAL_DEMO_MODE = False
WARNING_DEMO_MODE = False

SERVER_HOST = "10.1.7.73"
PORT = 5000
NODE_NAME = "PC_ANKITA"
PING_TARGET = "8.8.8.8"
SEND_INTERVAL_SECONDS = 2
HMAC_SECRET = b"secure-monitor-secret-key-2024"


def sign_payload(payload):
    return hmac.new(HMAC_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def get_temperature():
    try:
        sensors = psutil.sensors_temperatures()
    except (AttributeError, NotImplementedError):
        return None

    for entries in sensors.values():
        for entry in entries:
            current = getattr(entry, "current", None)
            if current is not None:
                return float(current)
    return None


def get_latency_ms():
    try:
        output = subprocess.run(
            ["ping", "-n", "1", "-w", "1000", PING_TARGET],
            capture_output=True,
            text=True,
            check=False,
        ).stdout
    except OSError:
        return 0

    match = re.search(r"time[=<]\s*(\d+)ms", output, re.IGNORECASE)
    if match:
        return int(match.group(1))
    return 0


def build_payload(seq):
    if CRITICAL_DEMO_MODE:
        cpu = 92
        memory = 95
        latency_ms = 650
        temperature = 88.0
    elif WARNING_DEMO_MODE:
        cpu = 75
        memory = 82
        latency_ms = 150
        temperature = 78.0
    else:
        cpu = psutil.cpu_percent(interval=1)
        memory = psutil.virtual_memory().percent
        latency_ms = get_latency_ms()
        temperature = get_temperature()

    return {
        "node": NODE_NAME,
        "cpu": cpu,
        "memory": memory,
        "latency": latency_ms,
        "temperature": temperature,
        "seq": seq,
        "sent_at": time.time(),
    }


def send_loop():
    seq = 0
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    print(f"[UDP CLIENT] Sending to {SERVER_HOST}:{PORT}")
    print("[UDP CLIENT] Security: HMAC-SHA256 signed packets")

    while True:
        payload_dict = build_payload(seq)
        payload_text = json.dumps(payload_dict)
        signature = sign_payload(payload_text)
        message = f"{payload_text}|{signature}"
        sock.sendto(message.encode("utf-8"), (SERVER_HOST, PORT))

        temperature = payload_dict["temperature"]
        temp_text = f" TEMP={temperature:.1f}C" if temperature is not None else ""
        print(
            f"Sent (seq={seq}): CPU={payload_dict['cpu']:.1f}% "
            f"MEM={payload_dict['memory']:.1f}% LAT={payload_dict['latency']}ms{temp_text}"
        )

        seq += 1
        time.sleep(SEND_INTERVAL_SECONDS)


if __name__ == "__main__":
    send_loop()
