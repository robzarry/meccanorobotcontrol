import time

import pytest
from fastapi.testclient import TestClient

from meccanoid import protocol, server
from meccanoid.server import create_app


@pytest.fixture
def client():
    with TestClient(create_app()) as c:
        yield c


def sent(client):
    return client.app.state.controller.robot.transport.sent


def test_page_and_assets_are_served(client):
    assert "Meccanoid" in client.get("/").text
    assert client.get("/static/app.js").status_code == 200
    assert client.get("/static/style.css").status_code == 200


def test_new_browser_receives_state(client):
    with client.websocket_connect("/ws") as ws:
        state = ws.receive_json()
    assert state["type"] == "state"
    assert state["mock"] is True
    assert state["connected"] is True
    assert state["joints"] == [128] * 8


def test_commands_reach_the_robot_and_state_is_broadcast(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "eyes", "r": 7, "g": 0, "b": 0})
        assert ws.receive_json()["eyes"] == [7, 0, 0]
        ws.send_json({"type": "joint", "servo": 3, "position": 40})
        assert ws.receive_json()["joints"][3] == 40
    assert protocol.eyes(7, 0, 0) in sent(client)


def test_bad_command_returns_error_not_disconnect(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "eyes", "r": 99, "g": 0, "b": 0})
        assert ws.receive_json()["type"] == "error"
        assert ws.receive_json()["type"] == "state"
        ws.send_json({"type": "wake"})
        assert ws.receive_json()["type"] == "state"


def test_wheels_stop_when_drive_messages_stop(client, monkeypatch):
    monkeypatch.setattr(server, "DRIVE_TIMEOUT", 0.2)
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "drive", "left": 100, "right": 100})
        assert ws.receive_json()["wheels"] == [100, 100]
        time.sleep(0.5)
        assert ws.receive_json()["wheels"] == [0, 0]
    assert sent(client)[-1] == protocol.stop_wheels()


def test_wheels_stop_when_the_driving_page_closes(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "drive", "left": 100, "right": 100})
        ws.receive_json()
    time.sleep(0.05)
    assert client.app.state.controller.robot.state.wheels == (0, 0)


def test_disconnect_and_reconnect(client):
    with client.websocket_connect("/ws") as ws:
        ws.receive_json()
        ws.send_json({"type": "disconnect"})
        while (s := ws.receive_json())["busy"]:
            pass
        assert s["connected"] is False
        ws.send_json({"type": "wake"})
        assert "not connected" in ws.receive_json()["message"]
        ws.receive_json()
        ws.send_json({"type": "connect"})
        while (s := ws.receive_json())["busy"]:
            pass
        assert s["connected"] is True
