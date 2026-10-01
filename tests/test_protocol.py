import pytest

from meccanoid import protocol
from meccanoid.protocol import MESSAGE_LENGTH


def body_and_checksum(message: bytes) -> tuple[bytes, int]:
    return message[:-2], int.from_bytes(message[-2:], "big")


@pytest.mark.parametrize("message", [
    protocol.wake(),
    protocol.servo_positions([0x80] * 8),
    protocol.servo_lights([7] * 8),
    protocol.wheels(100, -100),
    protocol.eyes(7, 7, 7),
    protocol.chest_lights([True, False, True, False]),
])
def test_every_message_is_20_bytes_with_valid_checksum(message):
    assert len(message) == MESSAGE_LENGTH
    body, total = body_and_checksum(message)
    assert total == sum(body)


def test_wake_matches_known_capture():
    # The same bytes pymecca and the Raspberry Pi forum thread send.
    expected = "19" + "1d" * 17 + "0206"
    assert protocol.wake().hex() == expected


def test_servo_positions_layout():
    msg = protocol.servo_positions([0, 1, 2, 3, 4, 5, 6, 0xFF])
    assert msg[0] == 0x08
    assert list(msg[1:9]) == [0, 1, 2, 3, 4, 5, 6, 0xFF]
    assert list(msg[9:18]) == [0x01] * 9


def test_wheels_split_direction_and_speed():
    msg = protocol.wheels(-200, 50)
    assert list(msg[:7]) == [0x0D, 0x02, 0x01, 200, 50, 0xFF, 0xFF]


def test_eyes_pack_green_and_red_into_one_byte():
    msg = protocol.eyes(red=5, green=3, blue=6)
    assert msg[3] == (3 << 3) | 5
    assert msg[4] == 6


@pytest.mark.parametrize("call", [
    lambda: protocol.servo_positions([0x80] * 7),
    lambda: protocol.servo_positions([256] + [0] * 7),
    lambda: protocol.servo_lights([8] * 8),
    lambda: protocol.wheels(256, 0),
    lambda: protocol.eyes(8, 0, 0),
    lambda: protocol.chest_lights([True] * 3),
])
def test_rejects_out_of_range_input(call):
    with pytest.raises(ValueError):
        call()
