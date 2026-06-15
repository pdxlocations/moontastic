from __future__ import annotations

import json
import re
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from .meshtastic_client import MeshtasticClient
from .models import Database


SEQUENCE_RE = re.compile(r"\bSEQ:(\d+)\b")


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass
class TestRequest:
    name: str
    callsign: str
    target: str
    channel: int
    interval_seconds: float
    packet_count: int
    timeout_seconds: float
    payload_prefix: str

    @classmethod
    def from_payload(cls, payload: dict[str, Any]) -> "TestRequest":
        packet_count = int(payload.get("packet_count", 5))
        interval_seconds = float(payload.get("interval_seconds", 15))
        timeout_seconds = float(payload.get("timeout_seconds", 20))
        if packet_count < 1 or packet_count > 500:
            raise ValueError("packet_count must be between 1 and 500")
        if interval_seconds < 1:
            raise ValueError("interval_seconds must be at least 1")
        if timeout_seconds < 1:
            raise ValueError("timeout_seconds must be at least 1")

        return cls(
            name=str(payload.get("name") or "Moonbounce test").strip(),
            callsign=str(payload.get("callsign") or "N0CALL").strip().upper(),
            target=str(payload.get("target") or "^all").strip(),
            channel=int(payload.get("channel", 0)),
            interval_seconds=interval_seconds,
            packet_count=packet_count,
            timeout_seconds=timeout_seconds,
            payload_prefix=str(payload.get("payload_prefix") or "MOON").strip().upper(),
        )


class TestRunner:
    def __init__(self, db: Database, client: MeshtasticClient):
        self.db = db
        self.client = client
        self.current_test_id: int | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._lock = threading.Lock()
        self.client.subscribe(self.record_received_packet)

    def start(self, request: TestRequest) -> dict[str, Any]:
        with self._lock:
            if self._thread and self._thread.is_alive():
                raise RuntimeError("A test is already running")

            with self.db.connect() as conn:
                cur = conn.execute(
                    """
                    INSERT INTO tests (
                        name, callsign, target, channel, interval_seconds, packet_count,
                        timeout_seconds, payload_prefix, status, started_at
                    )
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        request.name,
                        request.callsign,
                        request.target,
                        request.channel,
                        request.interval_seconds,
                        request.packet_count,
                        request.timeout_seconds,
                        request.payload_prefix,
                        "running",
                        utc_now(),
                    ),
                )
                test_id = int(cur.lastrowid)

            self.current_test_id = test_id
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, args=(test_id, request), daemon=True)
            self._thread.start()
            return self.get_test(test_id)

    def stop(self) -> None:
        self._stop.set()

    def status(self) -> dict[str, Any]:
        running = bool(self._thread and self._thread.is_alive())
        return {
            "running": running,
            "current_test_id": self.current_test_id if running else None,
            "interface": self.client.status(),
        }

    def _run(self, test_id: int, request: TestRequest) -> None:
        status = "completed"
        try:
            self.client.connect()
            for sequence in range(1, request.packet_count + 1):
                if self._stop.is_set():
                    status = "stopped"
                    break
                payload = self.format_payload(request, sequence)
                self.record_sent_packet(test_id, sequence, payload, request)
                self.client.send_text(payload, request.target, request.channel, want_ack=True)
                if self._stop.wait(request.interval_seconds):
                    status = "stopped"
                    break
            if not self._stop.is_set():
                time.sleep(min(request.timeout_seconds, 60))
        except Exception as exc:
            status = "failed"
            self.record_event(test_id, "error", str(exc), request.channel)
        finally:
            with self.db.connect() as conn:
                conn.execute(
                    "UPDATE tests SET status = ?, completed_at = ? WHERE id = ?",
                    (status, utc_now(), test_id),
                )

    def format_payload(self, request: TestRequest, sequence: int) -> str:
        timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        return f"{request.payload_prefix} {request.callsign} SEQ:{sequence} UTC:{timestamp}"

    def record_sent_packet(self, test_id: int, sequence: int, payload: str, request: TestRequest) -> None:
        self._insert_packet(
            test_id=test_id,
            sequence=sequence,
            direction="tx",
            payload=payload,
            node_id=request.target,
            channel=request.channel,
            ack=False,
        )

    def record_received_packet(self, packet: dict[str, Any]) -> None:
        decoded = packet.get("decoded") or {}
        payload = decoded.get("text") or decoded.get("payload") or json.dumps(decoded, sort_keys=True)
        sequence = self.extract_sequence(str(payload))
        self._insert_packet(
            test_id=self.current_test_id,
            sequence=sequence,
            direction="rx",
            payload=str(payload),
            node_id=packet.get("fromId") or packet.get("from"),
            channel=packet.get("channel"),
            rssi=packet.get("rxRssi"),
            snr=packet.get("rxSnr"),
            ack=bool(packet.get("wantAck") or packet.get("rxAck")),
            raw_json=json.dumps(packet, default=str, sort_keys=True),
        )

    def record_event(self, test_id: int, direction: str, payload: str, channel: int | None = None) -> None:
        self._insert_packet(test_id, None, direction, payload, None, channel, raw_json=None)

    def extract_sequence(self, payload: str) -> int | None:
        match = SEQUENCE_RE.search(payload)
        return int(match.group(1)) if match else None

    def _insert_packet(
        self,
        test_id: int | None,
        sequence: int | None,
        direction: str,
        payload: str,
        node_id: str | int | None,
        channel: int | None,
        rssi: float | None = None,
        snr: float | None = None,
        ack: bool = False,
        raw_json: str | None = None,
    ) -> None:
        with self.db.connect() as conn:
            conn.execute(
                """
                INSERT INTO packets (
                    test_id, sequence, direction, payload, node_id, channel,
                    rssi, snr, ack, created_at, raw_json
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    test_id,
                    sequence,
                    direction,
                    payload,
                    str(node_id) if node_id is not None else None,
                    channel,
                    rssi,
                    snr,
                    1 if ack else 0,
                    utc_now(),
                    raw_json,
                ),
            )

    def recent_tests(self, limit: int = 25) -> list[dict[str, Any]]:
        tests = self.db.query(
            """
            SELECT
                tests.*,
                SUM(CASE WHEN packets.direction = 'tx' THEN 1 ELSE 0 END) AS tx_count,
                SUM(CASE WHEN packets.direction = 'rx' THEN 1 ELSE 0 END) AS rx_count,
                ROUND(AVG(CASE WHEN packets.direction = 'rx' THEN packets.snr END), 2) AS avg_snr
            FROM tests
            LEFT JOIN packets ON packets.test_id = tests.id
            GROUP BY tests.id
            ORDER BY tests.id DESC
            LIMIT ?
            """,
            (limit,),
        )
        for test in tests:
            packets = self.db.query("SELECT * FROM packets WHERE test_id = ? ORDER BY id ASC", (test["id"],))
            summary = summarize_packets(annotate_packet_latencies(packets))
            test["avg_latency_ms"] = summary["avg_latency_ms"]
            test["min_latency_ms"] = summary["min_latency_ms"]
            test["max_latency_ms"] = summary["max_latency_ms"]
        return tests

    def get_test(self, test_id: int) -> dict[str, Any]:
        test = self.db.one("SELECT * FROM tests WHERE id = ?", (test_id,))
        if not test:
            raise KeyError(f"Test {test_id} not found")
        packets = self.db.query("SELECT * FROM packets WHERE test_id = ? ORDER BY id ASC", (test_id,))
        packets = annotate_packet_latencies(packets)
        test["packets"] = packets
        test["summary"] = summarize_packets(packets)
        return test


def annotate_packet_latencies(packets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tx_times: dict[int, datetime] = {}
    annotated: list[dict[str, Any]] = []
    for packet in packets:
        copy = dict(packet)
        sequence = copy.get("sequence")
        created_at = parse_timestamp(copy.get("created_at"))
        copy["latency_ms"] = None
        if copy.get("direction") == "tx" and sequence is not None and created_at:
            tx_times.setdefault(int(sequence), created_at)
        elif copy.get("direction") == "rx" and sequence is not None and created_at:
            tx_time = tx_times.get(int(sequence))
            if tx_time:
                latency_ms = (created_at - tx_time).total_seconds() * 1000
                if latency_ms >= 0:
                    copy["latency_ms"] = round(latency_ms, 1)
        annotated.append(copy)
    return annotated


def summarize_packets(packets: list[dict[str, Any]]) -> dict[str, Any]:
    tx = [p for p in packets if p["direction"] == "tx"]
    rx = [p for p in packets if p["direction"] == "rx"]
    tx_sequences = {p["sequence"] for p in tx if p["sequence"] is not None}
    rx_sequences = {p["sequence"] for p in rx if p["sequence"] is not None}
    heard = len(tx_sequences & rx_sequences)
    packet_loss = None
    if tx_sequences:
        packet_loss = round((1 - heard / len(tx_sequences)) * 100, 1)

    snr_values = [p["snr"] for p in rx if p["snr"] is not None]
    rssi_values = [p["rssi"] for p in rx if p["rssi"] is not None]
    latency_values = [p["latency_ms"] for p in rx if p.get("latency_ms") is not None]
    return {
        "tx": len(tx),
        "rx": len(rx),
        "matched_sequences": heard,
        "packet_loss_percent": packet_loss,
        "avg_snr": round(sum(snr_values) / len(snr_values), 2) if snr_values else None,
        "avg_rssi": round(sum(rssi_values) / len(rssi_values), 2) if rssi_values else None,
        "avg_latency_ms": round(sum(latency_values) / len(latency_values), 1) if latency_values else None,
        "min_latency_ms": round(min(latency_values), 1) if latency_values else None,
        "max_latency_ms": round(max(latency_values), 1) if latency_values else None,
    }
