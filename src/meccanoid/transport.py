"""Ways of delivering protocol messages to a robot.

* BleTransport talks to a real Meccanoid over Bluetooth LE (via bleak).
* MockTransport records messages so the app can run without hardware.
"""

from __future__ import annotations

import logging
from typing import Optional, Protocol

log = logging.getLogger(__name__)

# The handle pymecca writes to with gatttool. BlueZ/bleak may report the
# characteristic one handle lower (the declaration), so both are accepted.
KNOWN_HANDLES = (0x001F, 0x001E)

# Standard Bluetooth SIG services every device has; never the command channel.
_STANDARD_SERVICE_PREFIXES = ("00001800-", "00001801-", "0000180a-", "0000180f-")


class Transport(Protocol):
    @property
    def connected(self) -> bool: ...

    async def connect(self) -> None: ...

    async def disconnect(self) -> None: ...

    async def send(self, message: bytes) -> None: ...


class MockTransport:
    """Pretends to be a robot. Keeps every message it was sent."""

    def __init__(self) -> None:
        self.sent: list[bytes] = []
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def connect(self) -> None:
        self._connected = True
        log.info("mock robot connected")

    async def disconnect(self) -> None:
        self._connected = False
        log.info("mock robot disconnected")

    async def send(self, message: bytes) -> None:
        if not self._connected:
            raise ConnectionError("mock robot is not connected")
        self.sent.append(message)
        log.debug("mock send %s", message.hex())


class BleTransport:
    """A Meccanoid reached over Bluetooth LE.

    address: the MeccaBrain's MAC address (find it with scripts/probe.py).
    characteristic: optional UUID of the command characteristic. When omitted
        it is picked automatically: first by the known handle, otherwise the
        only writable characteristic outside the standard services.
    """

    def __init__(self, address: str, characteristic: Optional[str] = None,
                 with_response: bool = True) -> None:
        self.address = address
        self.characteristic_uuid = characteristic
        self.with_response = with_response
        self._client = None
        self._char = None

    @property
    def connected(self) -> bool:
        return self._client is not None and self._client.is_connected

    async def connect(self) -> None:
        from bleak import BleakClient

        client = BleakClient(self.address, disconnected_callback=self._on_disconnect)
        await client.connect()
        self._client = client
        self._char = self._find_characteristic(client)
        log.info("connected to %s; writing to %s (handle 0x%04x)",
                 self.address, self._char.uuid, self._char.handle)

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()
        self._client = None
        self._char = None

    async def send(self, message: bytes) -> None:
        if not self.connected or self._char is None:
            raise ConnectionError("robot is not connected")
        await self._client.write_gatt_char(self._char, message,
                                           response=self.with_response)

    def _on_disconnect(self, _client) -> None:
        log.warning("robot %s disconnected", self.address)

    def _find_characteristic(self, client):
        writable = [
            char
            for service in client.services
            for char in service.characteristics
            if {"write", "write-without-response"} & set(char.properties)
        ]
        if self.characteristic_uuid:
            for char in writable:
                if char.uuid.lower() == self.characteristic_uuid.lower():
                    return char
            raise LookupError(f"no writable characteristic {self.characteristic_uuid}")

        for handle in KNOWN_HANDLES:
            for char in writable:
                if char.handle == handle:
                    return char

        vendor = [c for c in writable
                  if not c.service_uuid.lower().startswith(_STANDARD_SERVICE_PREFIXES)]
        if len(vendor) == 1:
            return vendor[0]
        raise LookupError(
            "could not pick the command characteristic automatically; run "
            "scripts/probe.py and set MECCANOID_CHARACTERISTIC. Candidates: "
            + ", ".join(f"{c.uuid} (0x{c.handle:04x})" for c in writable)
        )
