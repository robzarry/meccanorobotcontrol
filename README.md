# Meccano Robot Control

Control a Meccano **Meccanoid G15** from a Raspberry Pi over Bluetooth LE, with a
web-based control panel you can open from any phone or laptop on your network.

There is no official API. The Bluetooth protocol comes from the community's
reverse-engineering work in [pymecca](https://github.com/iamsrp/pymecca).

> Status: foundation only. The protocol library, a mock robot and a hardware
> probe script are in place; the web GUI comes next.

## How it fits together

```
phone / laptop browser  ──Wi-Fi──>  Raspberry Pi (Python)  ──Bluetooth LE──>  Meccanoid
                                     src/meccanoid/
                                       protocol.py   builds the 20-byte messages
                                       transport.py  BLE (bleak) or mock robot
                                       robot.py      remembers state, sends commands
```

## What the robot understands

| Command | Byte | What it does |
|---|---|---|
| Servo positions | `0x08` | Sets all 8 arm servos at once (0-255, centre `0x80`) |
| Servo lights | `0x0c` | Sets each servo's LED colour (off, red, green, yellow, blue, magenta, cyan, white) |
| Wheels | `0x0d` | Left/right direction and speed |
| Eyes | `0x11` | Eye colour, 3 bits each for red, green and blue |
| Wake | `0x19` | Yawn, "I'm awake", arm wiggle |
| Chest lights | `0x1c` | Four chest lights on/off |

Every message is 18 bytes plus a 2-byte checksum (the sum of the 18 bytes).

## Setting up the Raspberry Pi

Any Pi with Bluetooth LE works (3, 4, 5, Zero 2 W) on Raspberry Pi OS Bookworm.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
git clone https://github.com/robzarry/meccanorobotcontrol.git
cd meccanorobotcontrol
uv sync
```

### First check: does the robot hear us?

Switch the robot on, then:

```bash
uv run scripts/probe.py scan                       # find the robot's address
uv run scripts/probe.py inspect AA:BB:CC:DD:EE:FF  # list its Bluetooth channels
uv run scripts/probe.py test AA:BB:CC:DD:EE:FF     # wake-up animation + eye colours
```

If `test` can't decide which channel to write to, pick the UUID from
`inspect` and pass `--characteristic <uuid>`.

## Developing without the robot

```bash
uv run pytest
```

The tests use `MockTransport`, which records messages instead of sending them.
