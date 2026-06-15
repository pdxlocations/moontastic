import os

from moontastic import create_app


def test_status_reports_default_simulator(tmp_path):
    os.environ["MOONTASTIC_DB"] = str(tmp_path / "test.sqlite3")
    app = create_app()

    response = app.test_client().get("/api/status")

    assert response.status_code == 200
    assert response.get_json()["interface"]["type"] == "sim"


def test_can_connect_and_disconnect_simulator(tmp_path):
    os.environ["MOONTASTIC_DB"] = str(tmp_path / "test.sqlite3")
    app = create_app()
    client = app.test_client()

    connected = client.post("/api/connection", json={"type": "sim"})
    disconnected = client.post("/api/connection/disconnect", json={})

    assert connected.status_code == 200
    assert connected.get_json()["connected"] is True
    assert disconnected.status_code == 200
    assert disconnected.get_json()["connected"] is False


def test_reception_map_endpoint_returns_grid(tmp_path):
    os.environ["MOONTASTIC_DB"] = str(tmp_path / "test.sqlite3")
    app = create_app()

    response = app.test_client().get("/api/reception-map?step_degrees=30")
    payload = response.get_json()

    assert response.status_code == 200
    assert payload["grid_step_degrees"] == 30
    assert payload["points"]
    assert 0 <= payload["coverage_percent"] <= 100


def test_listener_crud_and_planning_endpoint(tmp_path):
    os.environ["MOONTASTIC_DB"] = str(tmp_path / "test.sqlite3")
    app = create_app()
    client = app.test_client()

    created = client.post(
        "/api/listeners",
        json={
            "name": "Remote",
            "callsign": "K7ABC",
            "latitude": 45.0,
            "longitude": -122.0,
            "rx_gain_dbi": 14,
            "rx_sensitivity_dbm": -138,
        },
    )
    planning = client.get("/api/planning")
    deleted = client.delete(f"/api/listeners/{created.get_json()['id']}")

    assert created.status_code == 201
    assert planning.status_code == 200
    assert planning.get_json()["listeners"][0]["callsign"] == "K7ABC"
    assert "guardrails" in planning.get_json()
    assert deleted.get_json()["ok"] is True
