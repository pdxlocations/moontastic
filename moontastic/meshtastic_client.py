from __future__ import annotations

import random
import threading
import time
from dataclasses import dataclass
from typing import Callable, Protocol


PacketHandler = Callable[[dict], None]


class MeshtasticClient(Protocol):
    def connect(self) -> None:
        ...

    def close(self) -> None:
        ...

    def send_text(self, text: str, destination: str, channel: int, want_ack: bool = True) -> None:
        ...

    def subscribe(self, handler: PacketHandler) -> None:
        ...

    def status(self) -> dict:
        ...


@dataclass
class SimulatorClient:
    connected: bool = False
    handler: PacketHandler | None = None

    def connect(self) -> None:
        self.connected = True

    def close(self) -> None:
        self.connected = False

    def subscribe(self, handler: PacketHandler) -> None:
        self.handler = handler

    def send_text(self, text: str, destination: str, channel: int, want_ack: bool = True) -> None:
        if not self.connected:
            raise RuntimeError("Simulator is not connected")
        if self.handler:
            threading.Thread(
                target=self._deliver_echo,
                args=(text, destination, channel, want_ack),
                daemon=True,
            ).start()

    def _deliver_echo(self, text: str, destination: str, channel: int, want_ack: bool) -> None:
        time.sleep(random.uniform(0.25, 1.25))
        self.handler(
            {
                "fromId": destination or "!simulated",
                "decoded": {"text": f"ECHO {text}"},
                "rxSnr": round(random.uniform(4.0, 11.0), 2),
                "rxRssi": random.randint(-118, -76),
                "channel": channel,
                "wantAck": want_ack,
                "simulated": True,
            }
        )

    def status(self) -> dict:
        return {"type": "sim", "connected": self.connected}


class PythonMeshtasticClient:
    def __init__(
        self,
        interface_type: str,
        serial_port: str | None = None,
        tcp_host: str | None = None,
        ble_address: str | None = None,
    ):
        self.interface_type = interface_type
        self.serial_port = serial_port
        self.tcp_host = tcp_host
        self.ble_address = ble_address
        self.interface = None
        self.handler: PacketHandler | None = None

    def connect(self) -> None:
        if self.interface:
            return
        if self.interface_type == "serial":
            import meshtastic.serial_interface

            self.interface = meshtastic.serial_interface.SerialInterface(devPath=self.serial_port)
        elif self.interface_type == "tcp":
            import meshtastic.tcp_interface

            self.interface = meshtastic.tcp_interface.TCPInterface(hostname=self.tcp_host)
        elif self.interface_type == "ble":
            import meshtastic.ble_interface

            self.interface = meshtastic.ble_interface.BLEInterface(address=self.ble_address)
        else:
            raise ValueError(f"Unsupported interface type: {self.interface_type}")

        from pubsub import pub

        pub.subscribe(self._on_receive, "meshtastic.receive")

    def close(self) -> None:
        if self.interface:
            self.interface.close()
            self.interface = None

    def subscribe(self, handler: PacketHandler) -> None:
        self.handler = handler

    def send_text(self, text: str, destination: str, channel: int, want_ack: bool = True) -> None:
        if not self.interface:
            raise RuntimeError("Meshtastic interface is not connected")
        self.interface.sendText(
            text,
            destinationId=destination or "^all",
            channelIndex=channel,
            wantAck=want_ack,
        )

    def _on_receive(self, packet, interface=None) -> None:
        if self.handler:
            self.handler(packet)

    def status(self) -> dict:
        return {
            "type": self.interface_type,
            "connected": self.interface is not None,
            "serial_port": self.serial_port,
            "tcp_host": self.tcp_host,
            "ble_address": self.ble_address,
        }


class ConnectionManager:
    def __init__(
        self,
        interface_type: str,
        serial_port: str | None = None,
        tcp_host: str | None = None,
        ble_address: str | None = None,
    ):
        self._lock = threading.Lock()
        self._handler: PacketHandler | None = None
        self._client = build_client(
            interface_type,
            serial_port=serial_port,
            tcp_host=tcp_host,
            ble_address=ble_address,
        )

    def configure(
        self,
        interface_type: str,
        serial_port: str | None = None,
        tcp_host: str | None = None,
        ble_address: str | None = None,
    ) -> dict:
        with self._lock:
            self._client.close()
            self._client = build_client(
                interface_type,
                serial_port=serial_port,
                tcp_host=tcp_host,
                ble_address=ble_address,
            )
            if self._handler:
                self._client.subscribe(self._handler)
            self._client.connect()
            return self._client.status()

    def connect(self) -> None:
        with self._lock:
            self._client.connect()

    def close(self) -> None:
        with self._lock:
            self._client.close()

    def send_text(self, text: str, destination: str, channel: int, want_ack: bool = True) -> None:
        with self._lock:
            self._client.send_text(text, destination, channel, want_ack=want_ack)

    def subscribe(self, handler: PacketHandler) -> None:
        with self._lock:
            self._handler = handler
            self._client.subscribe(handler)

    def status(self) -> dict:
        with self._lock:
            return self._client.status()


def build_client(
    interface_type: str,
    serial_port: str | None = None,
    tcp_host: str | None = None,
    ble_address: str | None = None,
) -> MeshtasticClient:
    if interface_type == "sim":
        return SimulatorClient()
    return PythonMeshtasticClient(
        interface_type,
        serial_port=serial_port,
        tcp_host=tcp_host,
        ble_address=ble_address,
    )


def scan_ble_devices() -> list[dict[str, str | None]]:
    import meshtastic.ble_interface

    devices = meshtastic.ble_interface.BLEInterface.scan()
    return [{"name": device.name, "address": device.address} for device in devices]
