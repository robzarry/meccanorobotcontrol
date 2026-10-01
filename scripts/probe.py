"""Find the Meccanoid and check which Bluetooth channel accepts commands.

Run this on the Raspberry Pi with the robot switched on:

    uv run scripts/probe.py scan
    uv run scripts/probe.py inspect AA:BB:CC:DD:EE:FF
    uv run scripts/probe.py test AA:BB:CC:DD:EE:FF

`test` connects, plays the wake-up animation, then cycles the eye colour. If
the robot reacts, the protocol and characteristic are right.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from bleak import BleakClient, BleakScanner  # noqa: E402

from meccanoid import BleTransport, Robot  # noqa: E402


async def scan(seconds: float) -> None:
    print(f"Scanning for {seconds:.0f}s...")
    found = await BleakScanner.discover(timeout=seconds, return_adv=True)
    rows = sorted(found.values(), key=lambda pair: pair[1].rssi, reverse=True)
    for device, adv in rows:
        name = adv.local_name or device.name or "(no name)"
        hint = "  <-- likely" if "mecca" in name.lower() else ""
        print(f"{device.address}  rssi={adv.rssi:>4}  {name}{hint}")
    if not rows:
        print("Nothing found. Is Bluetooth on and the robot switched on?")


async def inspect(address: str) -> None:
    async with BleakClient(address) as client:
        print(f"Connected to {address}\n")
        for service in client.services:
            print(f"service {service.uuid}  {service.description}")
            for char in service.characteristics:
                props = ",".join(char.properties)
                print(f"  char 0x{char.handle:04x}  {char.uuid}  [{props}]")


async def test(address: str, characteristic: str | None) -> None:
    robot = Robot(BleTransport(address, characteristic))
    await robot.connect()
    try:
        print("Sending wake-up animation...")
        await robot.wake()
        await asyncio.sleep(4)
        for name, rgb in [("red", (7, 0, 0)), ("green", (0, 7, 0)),
                          ("blue", (0, 0, 7)), ("white", (7, 7, 7))]:
            print(f"Eyes {name}")
            await robot.set_eyes(*rgb)
            await asyncio.sleep(1)
        print("Done. Did the robot react?")
    finally:
        await robot.transport.disconnect()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p_scan = sub.add_parser("scan", help="list nearby Bluetooth LE devices")
    p_scan.add_argument("--seconds", type=float, default=8)
    p_inspect = sub.add_parser("inspect", help="list a device's services and characteristics")
    p_inspect.add_argument("address")
    p_test = sub.add_parser("test", help="send wake-up and eye colours")
    p_test.add_argument("address")
    p_test.add_argument("--characteristic", help="UUID to write to (default: auto)")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(name)s: %(message)s")
    if args.cmd == "scan":
        asyncio.run(scan(args.seconds))
    elif args.cmd == "inspect":
        asyncio.run(inspect(args.address))
    else:
        asyncio.run(test(args.address, args.characteristic))


if __name__ == "__main__":
    main()
