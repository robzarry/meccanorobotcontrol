"""Meccanoid G15 Bluetooth LE message encoding.

There is no official API. This mirrors the reverse-engineered protocol from
https://github.com/iamsrp/pymecca (Apache-2.0):

* Every message is 20 bytes: an 18-byte body followed by a 2-byte checksum.
* The first body byte is the command; the checksum is the 16-bit sum of the
  body bytes, big-endian.
* Messages are written to a single GATT characteristic (handle 0x001f on the
  robots pymecca was tested with).

Everything here is pure (bytes in, bytes out) so it can be tested without
hardware.
"""

from __future__ import annotations

from enum import IntEnum
from typing import Sequence

BODY_LENGTH = 18
MESSAGE_LENGTH = BODY_LENGTH + 2

SERVO_COUNT = 8
SERVO_CENTER = 0x80


class Command(IntEnum):
    SERVO_POSITIONS = 0x08
    SERVO_LIGHTS = 0x0C
    WHEELS = 0x0D
    EYES = 0x11
    WAKE = 0x19
    CHEST_LIGHTS = 0x1C


class Servo(IntEnum):
    """Index of each servo in the 8-slot servo chain."""

    UNKNOWN_0 = 0
    RIGHT_ELBOW = 1
    RIGHT_SHOULDER = 2
    LEFT_SHOULDER = 3
    LEFT_ELBOW = 4
    UNKNOWN_5 = 5
    UNKNOWN_6 = 6
    UNKNOWN_7 = 7


# These servos are mounted mirror-image, so a raw value of 0xff - x matches
# raw value x on the other side.
REVERSED_SERVOS = frozenset({Servo.RIGHT_ELBOW, Servo.LEFT_SHOULDER})


class ServoColor(IntEnum):
    OFF = 0
    RED = 1
    GREEN = 2
    YELLOW = 3
    BLUE = 4
    MAGENTA = 5
    CYAN = 6
    WHITE = 7


class WheelDirection(IntEnum):
    FORWARD = 0x01
    BACKWARD = 0x02


def checksum(body: Sequence[int]) -> int:
    return sum(body) & 0xFFFF


def _message(body: Sequence[int]) -> bytes:
    if len(body) != BODY_LENGTH:
        raise ValueError(f"body must be {BODY_LENGTH} bytes, got {len(body)}")
    for b in body:
        if not 0 <= b <= 0xFF:
            raise ValueError(f"byte out of range: {b}")
    total = checksum(body)
    return bytes(body) + bytes(((total >> 8) & 0xFF, total & 0xFF))


def _byte(value: int, name: str) -> int:
    if not 0 <= value <= 0xFF:
        raise ValueError(f"{name} must be 0-255, got {value}")
    return value


def servo_positions(positions: Sequence[int]) -> bytes:
    """Set all 8 servos at once. Values are raw 0-255 (0x80 is centre)."""
    if len(positions) != SERVO_COUNT:
        raise ValueError(f"need {SERVO_COUNT} positions, got {len(positions)}")
    body = [Command.SERVO_POSITIONS]
    body += [_byte(p, "servo position") for p in positions]
    body += [0x01] * 9
    return _message(body)


def servo_lights(colors: Sequence[int]) -> bytes:
    """Set the LED colour of all 8 servos (see ServoColor)."""
    if len(colors) != SERVO_COUNT:
        raise ValueError(f"need {SERVO_COUNT} colours, got {len(colors)}")
    for c in colors:
        if c not in ServoColor._value2member_map_:
            raise ValueError(f"servo colour must be 0-7, got {c}")
    body = [Command.SERVO_LIGHTS, *colors] + [0x04] * 9
    return _message(body)


def wheels(left: int, right: int) -> bytes:
    """Drive the wheels. Speeds are signed, -255 (full reverse) to 255."""

    def split(speed: int, name: str) -> tuple[int, int]:
        if not -0xFF <= speed <= 0xFF:
            raise ValueError(f"{name} speed must be -255..255, got {speed}")
        direction = WheelDirection.BACKWARD if speed < 0 else WheelDirection.FORWARD
        return direction, abs(speed)

    left_dir, left_speed = split(left, "left")
    right_dir, right_speed = split(right, "right")
    body = [Command.WHEELS, left_dir, right_dir, left_speed, right_speed, 0xFF, 0xFF]
    body += [0x00] * (BODY_LENGTH - len(body))
    return _message(body)


def stop_wheels() -> bytes:
    return wheels(0, 0)


def eyes(red: int, green: int, blue: int) -> bytes:
    """Set the eye colour. Each channel is 0-7 (3 bits)."""
    for name, v in (("red", red), ("green", green), ("blue", blue)):
        if not 0 <= v <= 7:
            raise ValueError(f"eye {name} must be 0-7, got {v}")
    body = [Command.EYES, 0x00, 0x00, (green << 3) | red, blue]
    body += [0x00] * (BODY_LENGTH - len(body))
    return _message(body)


def chest_lights(lights: Sequence[bool]) -> bytes:
    """Turn the 4 chest lights on or off."""
    if len(lights) != 4:
        raise ValueError(f"need 4 chest lights, got {len(lights)}")
    body = [Command.CHEST_LIGHTS, *(1 if on else 0 for on in lights)]
    body += [0x00] * (BODY_LENGTH - len(body))
    return _message(body)


def wake() -> bytes:
    """Play the wake-up animation (yawn, "I'm awake", arm wiggle)."""
    return _message([Command.WAKE] + [0x1D] * (BODY_LENGTH - 1))
