import hashlib
import hmac
import json
import socket
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timedelta, timezone
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

try:
    IST = ZoneInfo("Asia/Kolkata")
except ZoneInfoNotFoundError:
    IST = timezone(timedelta(hours=5, minutes=30), name="IST")

HOST = "0.0.0.0"
PORT = 5000
HTTP_HOST = "0.0.0.0"
HTTP_PORT = 8000
LOG_FILE = "events.log"
HMAC_SECRET = b"secure-monitor-secret-key-2024"
MAX_CLOCK_SKEW_SECONDS = 300
DASHBOARD_DIR = Path(__file__).parent / "dashboard"
MAX_RECENT_EVENTS = 80
OFFLINE_TIMEOUT_SECONDS = 10
PERFORMANCE_WINDOW_SECONDS = 10
VERBOSE_PACKET_LOGGING = True
SUMMARY_LOG_INTERVAL_SECONDS = 5

CPU_WARNING = 70
CPU_CRITICAL = 85
MEM_WARNING = 80
MEM_CRITICAL = 90
LAT_WARNING = 100
LAT_CRITICAL = 500
TEMP_WARNING = 75
TEMP_CRITICAL = 85

REQUIRED_FIELDS = {"node", "cpu", "memory", "latency", "seq", "sent_at"}
SEVERITY_RANK = {"CRITICAL": 0, "WARNING": 1, "INFO": 2}


def classify_event(cpu, memory, latency, temperature=None):
    if (
        cpu > CPU_CRITICAL
        or memory > MEM_CRITICAL
        or latency > LAT_CRITICAL
        or (temperature is not None and temperature > TEMP_CRITICAL)
    ):
        return "CRITICAL"
    if (
        cpu > CPU_WARNING
        or memory > MEM_WARNING
        or latency > LAT_WARNING
        or (temperature is not None and temperature > TEMP_WARNING)
    ):
        return "WARNING"
    return "INFO"


def sign_payload(payload):
    return hmac.new(HMAC_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def record_rejection(reason, addr=None):
    timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    source = f"{addr[0]}:{addr[1]}" if addr else "unknown"

    with state_lock:
        dashboard_state["performance"]["rejected_packets"] += 1
        dashboard_state["performance"]["rejections_by_reason"][reason] += 1

    print(f"[{timestamp}] [REJECTED] SRC:{source} REASON:{reason}")


def validate_event(event):
    missing_fields = sorted(REQUIRED_FIELDS - event.keys())
    if missing_fields:
        raise ValueError(f"missing fields: {', '.join(missing_fields)}")

    node = str(event["node"]).strip()
    if not node:
        raise ValueError("node name is empty")

    try:
        cpu = float(event["cpu"])
        memory = float(event["memory"])
        latency = int(event["latency"])
        seq = int(event["seq"])
        sent_at = float(event["sent_at"])
    except (TypeError, ValueError):
        raise ValueError("metric fields must be numeric")

    if seq < 0:
        raise ValueError("sequence number must be non-negative")

    if latency < 0:
        raise ValueError("latency must be non-negative")

    if not 0 <= cpu <= 100:
        raise ValueError("cpu must be between 0 and 100")

    if not 0 <= memory <= 100:
        raise ValueError("memory must be between 0 and 100")

    temperature = event.get("temperature")
    if temperature is not None:
        try:
            temperature = float(temperature)
        except (TypeError, ValueError):
            raise ValueError("temperature must be numeric when present")

    now = time.time()
    if abs(now - sent_at) > MAX_CLOCK_SKEW_SECONDS:
        raise ValueError("stale or replayed packet timestamp")

    return {
        "node": node,
        "cpu": cpu,
        "memory": memory,
        "latency": latency,
        "temperature": temperature,
        "seq": seq,
        "sent_at": sent_at,
    }


def verify_message(message_text):
    if "|" not in message_text:
        raise ValueError("missing HMAC signature")

    payload, received_signature = message_text.rsplit("|", 1)
    expected_signature = sign_payload(payload)
    if not hmac.compare_digest(expected_signature, received_signature):
        raise ValueError("invalid HMAC signature")

    try:
        event = json.loads(payload)
    except json.JSONDecodeError as exc:
        raise ValueError("malformed JSON payload") from exc

    if not isinstance(event, dict):
        raise ValueError("payload must decode to a JSON object")

    return validate_event(event)


node_state = defaultdict(
    lambda: {
        "last_seq": -1,
        "lost_packets": 0,
        "total_packets": 0,
        "last_severity": None,
        "last_seen_epoch": 0.0,
    }
)

dashboard_state = {
    "nodes": {},
    "stats": {"total_packets": 0, "info": 0, "warning": 0, "critical": 0},
    "recent_events": deque(maxlen=MAX_RECENT_EVENTS),
    "performance": {
        "active_nodes": 0,
        "offline_nodes": 0,
        "packets_per_second": 0.0,
        "average_delay_ms": 0.0,
        "max_delay_ms": 0.0,
        "rejected_packets": 0,
        "rejections_by_reason": defaultdict(int),
        "worst_packet_loss_percent": 0.0,
    },
    "started_at": datetime.now(IST).isoformat(),
}
state_lock = threading.Lock()
packet_timestamps = deque()
packet_delays_ms = deque()
last_summary_print = 0.0


def compute_live_performance(now_epoch):
    while packet_timestamps and now_epoch - packet_timestamps[0] > PERFORMANCE_WINDOW_SECONDS:
        packet_timestamps.popleft()

    while packet_delays_ms and now_epoch - packet_delays_ms[0][0] > PERFORMANCE_WINDOW_SECONDS:
        packet_delays_ms.popleft()

    nodes = dashboard_state["nodes"].values()
    active_nodes = 0
    offline_nodes = 0
    worst_packet_loss_percent = 0.0

    for node_data in nodes:
        is_online = (now_epoch - node_data["last_seen_epoch"]) <= OFFLINE_TIMEOUT_SECONDS
        node_data["is_online"] = is_online
        node_data["last_seen_age_seconds"] = round(now_epoch - node_data["last_seen_epoch"], 1)
        if is_online:
            active_nodes += 1
        else:
            offline_nodes += 1

        worst_packet_loss_percent = max(
            worst_packet_loss_percent,
            float(node_data.get("packet_loss", 0.0)),
        )

    dashboard_state["performance"]["active_nodes"] = active_nodes
    dashboard_state["performance"]["offline_nodes"] = offline_nodes
    dashboard_state["performance"]["packets_per_second"] = round(
        len(packet_timestamps) / PERFORMANCE_WINDOW_SECONDS,
        2,
    )
    if packet_delays_ms:
        delays = [delay for _, delay in packet_delays_ms]
        dashboard_state["performance"]["average_delay_ms"] = round(
            sum(delays) / len(delays), 2
        )
        dashboard_state["performance"]["max_delay_ms"] = round(max(delays), 2)
    else:
        dashboard_state["performance"]["average_delay_ms"] = 0.0
        dashboard_state["performance"]["max_delay_ms"] = 0.0
    dashboard_state["performance"]["worst_packet_loss_percent"] = round(
        worst_packet_loss_percent,
        1,
    )


def maybe_print_summary(now_epoch):
    global last_summary_print

    if VERBOSE_PACKET_LOGGING:
        return

    if now_epoch - last_summary_print < SUMMARY_LOG_INTERVAL_SECONDS:
        return

    perf = dashboard_state["performance"]
    timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    print(
        f"[{timestamp}] [SUMMARY] ACTIVE:{perf['active_nodes']} "
        f"OFFLINE:{perf['offline_nodes']} PPS:{perf['packets_per_second']:.2f} "
        f"AVG_DELAY:{perf['average_delay_ms']:.2f}ms MAX_DELAY:{perf['max_delay_ms']:.2f}ms "
        f"REJECTED:{perf['rejected_packets']}"
    )
    last_summary_print = now_epoch


def update_dashboard(event_record):
    node = event_record["node"]
    severity = event_record["severity"].lower()
    now_epoch = event_record["received_at_epoch"]

    with state_lock:
        dashboard_state["nodes"][node] = {
            "node": node,
            "cpu": event_record["cpu"],
            "memory": event_record["memory"],
            "latency": event_record["latency"],
            "temperature": event_record["temperature"],
            "severity": event_record["severity"],
            "seq": event_record["seq"],
            "packet_loss": event_record["packet_loss"],
            "total_packets": event_record["total_packets"],
            "source_ip": event_record["source_ip"],
            "source_port": event_record["source_port"],
            "timestamp": event_record["timestamp"],
            "status_change": event_record["status_change"],
            "delay_ms": event_record["delay_ms"],
            "last_seen": event_record["last_seen"],
            "last_seen_epoch": now_epoch,
            "is_online": True,
            "last_seen_age_seconds": 0.0,
        }
        dashboard_state["stats"]["total_packets"] += 1
        dashboard_state["stats"][severity] += 1
        dashboard_state["recent_events"].appendleft(event_record)

        packet_timestamps.append(now_epoch)
        packet_delays_ms.append((now_epoch, event_record["delay_ms"]))
        compute_live_performance(now_epoch)
        maybe_print_summary(now_epoch)


def build_dashboard_payload():
    with state_lock:
        now_epoch = time.time()
        compute_live_performance(now_epoch)
        nodes = sorted(
            dashboard_state["nodes"].values(),
            key=lambda item: (
                0 if item["is_online"] else 1,
                SEVERITY_RANK.get(item["severity"], 99),
                -item["last_seen_epoch"],
                item["node"].lower(),
            ),
        )
        performance = dict(dashboard_state["performance"])
        performance["rejections_by_reason"] = dict(performance["rejections_by_reason"])
        return {
            "generated_at": datetime.now(IST).isoformat(),
            "started_at": dashboard_state["started_at"],
            "stats": dict(dashboard_state["stats"]),
            "performance": performance,
            "nodes": nodes,
            "recent_events": list(dashboard_state["recent_events"]),
        }


def process_event(event, addr):
    node = event["node"]
    cpu = event["cpu"]
    memory = event["memory"]
    latency = event["latency"]
    seq = event["seq"]
    temperature = event["temperature"]
    received_at_epoch = time.time()

    state = node_state[node]

    if state["last_seq"] >= 0:
        gap = seq - state["last_seq"] - 1
        if gap > 0:
            state["lost_packets"] += gap
            print(
                f"[PACKET LOSS] NODE:{node} LOST:{gap} "
                f"SEQ_RANGE:{state['last_seq'] + 1}-{seq - 1}"
            )
        elif seq <= state["last_seq"]:
            record_rejection("out-of-order or duplicate sequence", addr)
            return

    state["total_packets"] += 1
    state["last_seen_epoch"] = received_at_epoch
    state["last_seq"] = seq

    severity = classify_event(cpu, memory, latency, temperature)
    timestamp = datetime.now(IST).strftime("%Y-%m-%d %H:%M:%S IST")
    delay_ms = max(0.0, round((received_at_epoch - event["sent_at"]) * 1000, 2))

    previous = state["last_severity"]
    edge_tag = ""
    if severity != previous:
        edge_tag = f" [EDGE: {previous or 'START'} -> {severity}]"
    state["last_severity"] = severity

    metrics = (
        f"NODE:{node} CPU:{cpu:.1f}% MEM:{memory:.1f}% LAT:{latency}ms "
        f"SEQ:{seq} SRC:{addr[0]}:{addr[1]} DELAY:{delay_ms:.2f}ms"
    )
    if temperature is not None:
        metrics += f" TEMP:{temperature:.1f}C"

    log_entry = f"[{timestamp}] [{severity}] {metrics}{edge_tag}"
    if VERBOSE_PACKET_LOGGING:
        print(log_entry)

    with open(LOG_FILE, "a", encoding="utf-8") as log_file:
        log_file.write(log_entry + "\n")

    packet_loss_rate = 0.0
    if state["total_packets"]:
        packet_loss_rate = (state["lost_packets"] / state["total_packets"]) * 100

    update_dashboard(
        {
            "timestamp": timestamp,
            "node": node,
            "severity": severity,
            "cpu": round(cpu, 1),
            "memory": round(memory, 1),
            "latency": latency,
            "temperature": round(temperature, 1) if temperature is not None else None,
            "seq": seq,
            "source_ip": addr[0],
            "source_port": addr[1],
            "packet_loss": round(packet_loss_rate, 1),
            "total_packets": state["total_packets"],
            "status_change": edge_tag.strip() if edge_tag else "",
            "delay_ms": delay_ms,
            "last_seen": datetime.now(IST).isoformat(),
            "received_at_epoch": received_at_epoch,
        }
    )


class DashboardHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR), **kwargs)

    def do_GET(self):
        parsed = urlparse(self.path)
        if parsed.path == "/api/dashboard":
            payload = build_dashboard_payload()
            body = json.dumps(payload).encode("utf-8")

            self.send_response(200)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path == "/":
            self.path = "/index.html"

        super().do_GET()

    def log_message(self, format_text, *args):
        return


def start_http_server():
    DASHBOARD_DIR.mkdir(exist_ok=True)
    httpd = ThreadingHTTPServer((HTTP_HOST, HTTP_PORT), DashboardHandler)
    print(f"[DASHBOARD] Open http://localhost:{HTTP_PORT}")
    httpd.serve_forever()


def start_udp_server():
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind((HOST, PORT))

    print(f"[UDP SERVER] Listening on {HOST}:{PORT}")
    print("[UDP SERVER] Security: HMAC-SHA256 + packet timestamp validation")
    print(
        "[UDP SERVER] Authenticated UDP is enabled here. "
        "True SSL-over-UDP would require DTLS."
    )

    while True:
        addr = None
        try:
            raw_data, addr = sock.recvfrom(8192)
            message_text = raw_data.decode("utf-8")
            event = verify_message(message_text)
            process_event(event, addr)
        except UnicodeDecodeError:
            record_rejection("payload is not valid UTF-8", addr)
        except ValueError as exc:
            record_rejection(str(exc), addr)
        except OSError as exc:
            print(f"[SERVER ERROR] {exc}")


def start_server():
    threading.Thread(target=start_http_server, daemon=True).start()
    start_udp_server()


if __name__ == "__main__":
    start_server()
