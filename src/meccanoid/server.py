"""Web control panel for the Meccanoid.

Serves a single page and a WebSocket at /ws. Browsers send JSON commands;
after every change the server broadcasts the full robot state to every open
browser, so several phones/laptops stay in sync.

Configuration (environment variables or command-line flags):
    MECCANOID_ADDRESS         Bluetooth address of the robot. Omit for the mock.
    MECCANOID_CHARACTERISTIC  Optional UUID of the command characteristic.

Safety: wheels are a dead-man's switch. The page re-sends "drive" while a
direction is held; if nothing arrives for DRIVE_TIMEOUT seconds (button
released, tab closed, Wi-Fi dropped) the wheels are stopped.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Optional

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from .protocol import Servo, ServoColor
from .robot import Robot
from .transport import BleTransport, MockTransport

log = logging.getLogger(__name__)

WEB_DIR = Path(__file__).parent / "web"
DRIVE_TIMEOUT = 0.6
WATCHDOG_INTERVAL = 0.1


class Controller:
    """Owns the robot, applies commands from browsers, tells them what changed."""

    def __init__(self, robot: Robot, mock: bool, address: Optional[str]) -> None:
        self.robot = robot
        self.mock = mock
        self.address = address
        self.clients: set[WebSocket] = set()
        self.last_drive = 0.0
        self.busy = False  # connecting / disconnecting

    def state(self) -> dict[str, Any]:
        s = self.robot.state
        return {
            "type": "state",
            "connected": self.robot.connected,
            "busy": self.busy,
            "mock": self.mock,
            "address": self.address,
            "joints": [self.robot.joint_position(Servo(i)) for i in range(len(s.servos))],
            "servo_colors": [int(c) for c in s.servo_colors],
            "eyes": list(s.eyes),
            "chest": list(s.chest),
            "wheels": list(s.wheels),
        }

    async def broadcast(self, message: Optional[dict] = None) -> None:
        message = message or self.state()
        for ws in list(self.clients):
            try:
                await ws.send_json(message)
            except Exception:
                self.clients.discard(ws)

    async def handle(self, msg: dict[str, Any]) -> None:
        kind = msg.get("type")
        r = self.robot
        if kind == "connect":
            await self._set_connection(True)
            return
        if kind == "disconnect":
            await self._set_connection(False)
            return
        if not r.connected:
            raise ConnectionError("robot is not connected")

        if kind == "wake":
            await r.wake()
        elif kind == "joint":
            await r.set_joint(Servo(int(msg["servo"])), int(msg["position"]))
        elif kind == "servo_color":
            await r.set_servo_color(Servo(int(msg["servo"])), ServoColor(int(msg["color"])))
        elif kind == "eyes":
            await r.set_eyes(int(msg["r"]), int(msg["g"]), int(msg["b"]))
        elif kind == "chest":
            await r.set_chest(int(msg["index"]), bool(msg["on"]))
        elif kind == "drive":
            self.last_drive = time.monotonic()
            left, right = int(msg["left"]), int(msg["right"])
            if (left, right) != r.state.wheels:  # repeats only refresh the timer
                await r.drive(left, right)
            else:
                return
        elif kind == "stop":
            await r.stop()
        elif kind == "center":
            await r.center_joints()
        else:
            raise ValueError(f"unknown command {kind!r}")
        await self.broadcast()

    async def _set_connection(self, on: bool) -> None:
        if on == self.robot.connected or self.busy:
            return
        self.busy = True
        await self.broadcast()
        try:
            await (self.robot.connect() if on else self.robot.disconnect())
        finally:
            self.busy = False
            await self.broadcast()

    async def watchdog(self) -> None:
        while True:
            await asyncio.sleep(WATCHDOG_INTERVAL)
            r = self.robot
            if (r.connected and r.state.wheels != (0, 0)
                    and time.monotonic() - self.last_drive > DRIVE_TIMEOUT):
                log.info("drive timed out; stopping wheels")
                with contextlib.suppress(Exception):
                    await r.stop()
                await self.broadcast()


def create_app(address: Optional[str] = None, characteristic: Optional[str] = None,
               autoconnect: bool = True) -> FastAPI:
    if address:
        transport = BleTransport(address, characteristic)
    else:
        transport = MockTransport()
    controller = Controller(Robot(transport), mock=address is None, address=address)

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if autoconnect:
            try:
                await controller.robot.connect()
            except Exception as e:  # stay up so the user can retry from the page
                log.error("could not connect to robot: %s", e)
        task = asyncio.create_task(controller.watchdog())
        yield
        task.cancel()
        with contextlib.suppress(Exception):
            await controller.robot.disconnect()

    app = FastAPI(title="Meccanoid control", lifespan=lifespan)
    app.state.controller = controller

    @app.get("/")
    async def index() -> FileResponse:
        return FileResponse(WEB_DIR / "index.html")

    @app.websocket("/ws")
    async def ws_endpoint(ws: WebSocket) -> None:
        await ws.accept()
        controller.clients.add(ws)
        await ws.send_json(controller.state())
        try:
            while True:
                msg = await ws.receive_json()
                try:
                    await controller.handle(msg)
                except Exception as e:
                    log.warning("command %s failed: %s", msg.get("type"), e)
                    await ws.send_json({"type": "error", "message": str(e)})
                    await ws.send_json(controller.state())
        except WebSocketDisconnect:
            pass
        finally:
            controller.clients.discard(ws)
            # Losing the page that was driving must not leave the robot rolling.
            if controller.robot.connected and controller.robot.state.wheels != (0, 0):
                with contextlib.suppress(Exception):
                    await controller.robot.stop()
                await controller.broadcast()

    app.mount("/static", StaticFiles(directory=WEB_DIR), name="static")
    return app


def main() -> None:
    import uvicorn

    parser = argparse.ArgumentParser(description="Meccanoid web control panel")
    parser.add_argument("--address", default=os.environ.get("MECCANOID_ADDRESS"),
                        help="robot Bluetooth address (omit to use the mock robot)")
    parser.add_argument("--characteristic", default=os.environ.get("MECCANOID_CHARACTERISTIC"))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    if not args.address:
        log.info("no robot address given: using the mock robot")
    app = create_app(args.address, args.characteristic)
    uvicorn.run(app, host=args.host, port=args.port)


if __name__ == "__main__":
    main()
