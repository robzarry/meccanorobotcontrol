# Meccano Robot Control

Control a Meccano **Meccanoid G15** from a Raspberry Pi over Bluetooth LE, with a
web-based control panel you can open from any phone or laptop on your network.

There is no official API. The Bluetooth protocol comes from the community's
reverse-engineering work in [pymecca](https://github.com/iamsrp/pymecca).

> Status: protocol library, hardware probe and web control panel are in place.
> Not yet verified against a real G15; see "First check" below.

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

## The control panel

On the Pi, with the robot's address from `probe.py scan`:

```bash
uv run meccanoid-web --address AA:BB:CC:DD:EE:FF
```

Then open `http://<pi-hostname>.local:8000` on your phone or laptop. You can
also set `MECCANOID_ADDRESS` (and `MECCANOID_CHARACTERISTIC` if needed)
instead of passing flags.

The panel has a live drawing of the robot, a hold-to-drive pad (arrow keys or
WASD on a keyboard), arm sliders, eye / chest / servo light controls, and a
STOP button. Every open browser shows the same state.

**Safety:** the wheels only run while a drive button is held. The page
re-sends the command every 0.2 s; if the server hears nothing for 0.6 s
(button released, tab switched, phone locked, Wi-Fi dropped) it stops the
wheels. Closing the page that was driving also stops them.

**No login:** anyone on your network who can reach port 8000 can drive the
robot. Fine for a home network; don't expose it to the internet.

## Developing without the robot

Leave out the address and the panel runs against a mock robot:

```bash
uv run meccanoid-web
uv run pytest
```

`MockTransport` records messages instead of sending them over Bluetooth.
