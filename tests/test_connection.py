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
