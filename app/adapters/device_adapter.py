"""Penghubung ke perangkat fisik (saklar lampu/AC).

Semua kode lain hanya bergantung pada DeviceAdapter. Saat protokol asli
sudah diputuskan (HTTP ke ESP32, MQTT, Home Assistant, dst.), cukup buat
kelas baru dengan method send() yang sama lalu ganti get_adapter().
"""
from typing import Protocol

from app.models import CommandAction, Device


class DeviceError(Exception):
    """Perangkat gagal menerima atau menjalankan perintah."""


class DeviceAdapter(Protocol):
    def send(self, device: Device, action: CommandAction) -> None:
        """Kirim perintah ke perangkat. Raise DeviceError kalau gagal."""


class SimulatedDeviceAdapter:
    """Simulasi: selalu berhasil, kecuali id perangkat ada di fail_device_ids."""

    def __init__(self, fail_device_ids: set[int] | None = None):
        self.fail_device_ids = fail_device_ids or set()
        self.sent: list[tuple[int, str]] = []

    def send(self, device: Device, action: CommandAction) -> None:
        if device.id in self.fail_device_ids:
            raise DeviceError(f"simulasi: perangkat {device.id} gagal merespons")
        self.sent.append((device.id, action.value))


_default_adapter = SimulatedDeviceAdapter()


def get_adapter() -> DeviceAdapter:
    """MQTT jika MQTT_ENABLED dan bridge sudah jalan; selain itu simulasi."""
    from app.adapters.mqtt_bridge import MqttDeviceAdapter, get_bridge  # hindari impor melingkar

    bridge = get_bridge()
    if bridge is not None:
        return MqttDeviceAdapter(bridge)
    return _default_adapter
