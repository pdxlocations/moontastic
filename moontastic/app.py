from __future__ import annotations

from pathlib import Path

from flask import Flask, jsonify, render_template, request

from .config import load_config
from .meshtastic_client import ConnectionManager, scan_ble_devices
from .models import Database
from .moon import LinkBudget, Station, moon_prediction
from .runner import TestRequest, TestRunner


def create_app() -> Flask:
    config = load_config()
    project_root = Path(__file__).resolve().parent.parent
    app = Flask(
        __name__,
        template_folder=str(project_root / "templates"),
        static_folder=str(project_root / "static"),
    )
    app.config["SECRET_KEY"] = config.secret_key

    db = Database(config.database_path)
    client = ConnectionManager(
        config.interface_type,
        serial_port=config.serial_port,
        tcp_host=config.tcp_host,
        ble_address=config.ble_address,
    )
    runner = TestRunner(db, client)

    app.extensions["moontastic_db"] = db
    app.extensions["moontastic_runner"] = runner

    @app.get("/")
    def index():
        return render_template("index.html")

    @app.get("/api/status")
    def api_status():
        return jsonify(runner.status())

    @app.post("/api/connection")
    def api_connect():
        payload = request.get_json(silent=True) or {}
        interface_type = str(payload.get("type") or "sim").lower()
        if interface_type not in {"sim", "tcp", "serial", "ble"}:
            return jsonify({"error": "type must be sim, tcp, serial, or ble"}), 400
        try:
            status = client.configure(
                interface_type,
                serial_port=str(payload.get("serial_port") or "").strip() or None,
                tcp_host=str(payload.get("tcp_host") or "").strip() or None,
                ble_address=str(payload.get("ble_address") or "").strip() or None,
            )
            return jsonify(status)
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.post("/api/connection/disconnect")
    def api_disconnect():
        client.close()
        return jsonify(client.status())

    @app.get("/api/connection/ble/scan")
    def api_ble_scan():
        try:
            return jsonify(scan_ble_devices())
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    @app.get("/api/moon")
    def api_moon():
        station = Station(
            latitude=float(request.args.get("lat", config.station_latitude)),
            longitude=float(request.args.get("lon", config.station_longitude)),
            elevation_m=float(request.args.get("elevation_m", config.station_elevation_m)),
        )
        link = LinkBudget(
            frequency_mhz=float(request.args.get("frequency_mhz", config.frequency_mhz)),
            tx_power_dbm=float(request.args.get("tx_power_dbm", config.tx_power_dbm)),
            tx_gain_dbi=float(request.args.get("tx_gain_dbi", config.tx_gain_dbi)),
            rx_gain_dbi=float(request.args.get("rx_gain_dbi", config.rx_gain_dbi)),
            rx_sensitivity_dbm=float(request.args.get("rx_sensitivity_dbm", config.rx_sensitivity_dbm)),
        )
        return jsonify(moon_prediction(station, link))

    @app.get("/api/tests")
    def api_tests():
        return jsonify(runner.recent_tests())

    @app.post("/api/tests")
    def api_start_test():
        try:
            test_request = TestRequest.from_payload(request.get_json(silent=True) or {})
            return jsonify(runner.start(test_request)), 201
        except ValueError as exc:
            return jsonify({"error": str(exc)}), 400
        except RuntimeError as exc:
            return jsonify({"error": str(exc)}), 409

    @app.post("/api/tests/current/stop")
    def api_stop_test():
        runner.stop()
        return jsonify({"ok": True})

    @app.get("/api/tests/<int:test_id>")
    def api_test(test_id: int):
        try:
            return jsonify(runner.get_test(test_id))
        except KeyError:
            return jsonify({"error": "not found"}), 404

    @app.post("/api/send")
    def api_send():
        payload = request.get_json(silent=True) or {}
        text = str(payload.get("text") or "").strip()
        if not text:
            return jsonify({"error": "text is required"}), 400
        destination = str(payload.get("target") or "^all")
        channel = int(payload.get("channel", 0))
        try:
            client.connect()
            client.send_text(text, destination, channel, want_ack=bool(payload.get("want_ack", True)))
            return jsonify({"ok": True})
        except Exception as exc:
            return jsonify({"error": str(exc)}), 500

    return app
