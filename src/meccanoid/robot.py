"""High-level robot control.

The protocol sets all 8 servos (or servo lights) in one message, so moving a
single joint means re-sending the others too. Robot keeps that state.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field

from . import protocol
from .protocol import REVERSED_SERVOS, SERVO_CENTER, SERVO_COUNT, Servo, ServoColor
from .transport import Transport


@dataclass
class RobotState:
    servos: list[int] = field(default_factory=lambda: [SERVO_CENTER] * SERVO_COUNT)
    servo_colors: list[int] = field(default_factory=lambda: [ServoColor.OFF] * SERVO_COUNT)
    eyes: tuple[int, int, int] = (7, 7, 7)
    chest: list[bool] = field(default_factory=lambda: [False] * 4)
    wheels: tuple[int, int] = (0, 0)


class Robot:
    def __init__(self, transport: Transport) -> None:
        self.transport = transport
        self.state = RobotState()
        # One message at a time; BLE writes must not interleave.
        self._lock = asyncio.Lock()

    @property
    def connected(self) -> bool:
        return self.transport.connected

    async def connect(self) -> None:
        await self.transport.connect()

    async def disconnect(self) -> None:
        if self.transport.connected:
            await self.stop()
        await self.transport.disconnect()

    async def _send(self, message: bytes) -> None:
        async with self._lock:
            await self.transport.send(message)

    async def wake(self) -> None:
        await self._send(protocol.wake())

    async def set_joint(self, servo: Servo, position: int) -> None:
        """Move one joint. position is 0-255; mirrored joints are corrected
        so the same value means the same pose on both arms."""
        raw = 0xFF - position if servo in REVERSED_SERVOS else position
        self.state.servos[servo] = raw
        await self._send(protocol.servo_positions(self.state.servos))

    async def set_servo_color(self, servo: Servo, color: ServoColor) -> None:
        self.state.servo_colors[servo] = color
        await self._send(protocol.servo_lights(self.state.servo_colors))

    async def set_eyes(self, red: int, green: int, blue: int) -> None:
        self.state.eyes = (red, green, blue)
        await self._send(protocol.eyes(red, green, blue))

    async def set_chest(self, index: int, on: bool) -> None:
        self.state.chest[index] = on
        await self._send(protocol.chest_lights(self.state.chest))

    async def drive(self, left: int, right: int) -> None:
        self.state.wheels = (left, right)
        await self._send(protocol.wheels(left, right))

    async def stop(self) -> None:
        self.state.wheels = (0, 0)
        await self._send(protocol.stop_wheels())
