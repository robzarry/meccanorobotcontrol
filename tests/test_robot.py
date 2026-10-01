import pytest

from meccanoid import MockTransport, Robot, Servo
from meccanoid import protocol


@pytest.fixture
async def robot():
    r = Robot(MockTransport())
    await r.connect()
    return r


async def test_moving_one_joint_resends_the_others(robot):
    await robot.set_joint(Servo.RIGHT_SHOULDER, 0x20)
    await robot.set_joint(Servo.LEFT_ELBOW, 0x30)
    last = robot.transport.sent[-1]
    assert last[1 + Servo.RIGHT_SHOULDER] == 0x20
    assert last[1 + Servo.LEFT_ELBOW] == 0x30


async def test_mirrored_joints_are_reversed(robot):
    await robot.set_joint(Servo.LEFT_SHOULDER, 0x20)
    assert robot.state.servos[Servo.LEFT_SHOULDER] == 0xFF - 0x20


async def test_disconnect_stops_wheels_first(robot):
    await robot.drive(100, 100)
    await robot.disconnect()
    assert robot.transport.sent[-1] == protocol.stop_wheels()
    assert not robot.connected


async def test_send_when_disconnected_fails():
    robot = Robot(MockTransport())
    with pytest.raises(ConnectionError):
        await robot.wake()
