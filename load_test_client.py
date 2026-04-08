import argparse
import hashlib
import hmac
import json
import socket
import time

HMAC_SECRET = b"secure-monitor-secret-key-2024"


def sign_payload(payload):
    return hmac.new(HMAC_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def build_metrics(index, seq, mode):
    if mode == "info":
        return {
            "cpu": 24 + (index % 7),
            "memory": 44 + (index % 12),
            "latency": 35 + (seq % 15),
            "temperature": 49.0 + (index % 5),
        }
    if mode == "warning":
        return {
            "cpu": 75 + (index % 6),
            "memory": 82 + (seq % 4),
            "latency": 135 + (index % 20),
            "temperature": 77.0 + (index % 4),
        }
    if mode == "critical":
        return {
            "cpu": 92 + (index % 4),
            "memory": 94 + (seq % 3),
            "latency": 620 + (index % 35),
            "temperature": 88.0 + (index % 3),
        }

    if seq % 10 == 0:
        return build_metrics(index, seq, "critical")
    if seq % 3 == 0:
        return build_metrics(index, seq, "warning")
    return build_metrics(index, seq, "info")


def main():
    parser = argparse.ArgumentParser(
        description="Simulate many UDP NEMS nodes for repeatable performance testing."
    )
    parser.add_argument("--server-host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--nodes", type=int, default=5)
    parser.add_argument("--interval", type=float, default=1.0)
    parser.add_argument("--duration", type=int, default=30)
    parser.add_argument(
        "--mode",
        choices=["info", "warning", "critical", "mixed"],
        default="mixed",
    )
    parser.add_argument("--node-prefix", default="load-node")
    args = parser.parse_args()

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sequences = {f"{args.node_prefix}-{index + 1:02d}": 0 for index in range(args.nodes)}

    print(
        f"[LOAD TEST] Sending to {args.server_host}:{args.port} | "
        f"NODES={args.nodes} | INTERVAL={args.interval}s | DURATION={args.duration}s | "
        f"MODE={args.mode}"
    )

    start_time = time.time()
    cycle_count = 0
    while time.time() - start_time < args.duration:
        for index, node_name in enumerate(sequences.keys()):
            seq = sequences[node_name]
            metrics = build_metrics(index, seq, args.mode)
            payload = {
                "node": node_name,
                "cpu": metrics["cpu"],
                "memory": metrics["memory"],
                "latency": metrics["latency"],
                "temperature": metrics["temperature"],
                "seq": seq,
                "sent_at": time.time(),
            }
            payload_text = json.dumps(payload)
            signature = sign_payload(payload_text)
            message = f"{payload_text}|{signature}"
            sock.sendto(message.encode("utf-8"), (args.server_host, args.port))
            sequences[node_name] = seq + 1

        cycle_count += 1
        if cycle_count == 1 or cycle_count % 5 == 0:
            total_packets = sum(sequences.values())
            print(
                f"[LOAD TEST] cycles={cycle_count} total_packets_sent={total_packets}"
            )
        time.sleep(args.interval)

    print("[LOAD TEST] Completed.")


if __name__ == "__main__":
    main()
