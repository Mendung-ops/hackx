"""Jembatan MQTT: menerima data dari vision/panel/acunit, mengirim perintah ke perangkat.

Rule engine tetap tidak tahu soal MQTT. Bridge hanya (1) meneruskan pesan masuk ke
`services/mqtt_handler.handle_message` dan (2) menjadi DeviceAdapter yang
mem-publish perintah ke `{prefix}/cmd/{device_id}`.
"""
import json
import logging
import threading
import uuid

import paho.mqtt.client as mqtt

from app.adapters.device_adapter import DeviceError
from app.db.session import SessionLocal, settings
from app.models import CommandAction, Device
from app.services.ack_tracker import AckTracker
from app.services.control_service import fail_unacked
from app.services.mqtt_handler import handle_message

log = logging.getLogger("hackx.mqtt")


class MqttBridge:
    def __init__(self) -> None:
        self.prefix = settings.mqtt_topic_prefix
        self.connected = False
        self.tracker = AckTracker(settings.mqtt_ack_timeout_seconds)
        self._stop_evt = threading.Event()
        self._reaper: threading.Thread | None = None
        self._client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2, client_id=settings.mqtt_client_id
        )
        if settings.mqtt_username:
            self._client.username_pw_set(settings.mqtt_username, settings.mqtt_password)
        # Last Will: broker menandai engine offline kalau koneksi putus mendadak.
        self._client.will_set(f"{self.prefix}/status/engine", "offline", qos=1, retain=True)
        self._client.reconnect_delay_set(min_delay=1, max_delay=10)
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.on_message = self._on_message

    # -- siklus hidup -------------------------------------------------------
    def start(self) -> None:
        # connect_async + loop_start: server tetap naik walau broker belum siap,
        # lalu paho menyambung ulang otomatis.
        self._client.connect_async(settings.mqtt_host, settings.mqtt_port, keepalive=30)
        self._client.loop_start()
        if self.tracker.enabled:
            self._reaper = threading.Thread(target=self._reap, name="mqtt-ack", daemon=True)
            self._reaper.start()

    def stop(self) -> None:
        self._stop_evt.set()
        if self.connected:
            self._client.publish(f"{self.prefix}/status/engine", "offline", qos=1, retain=True)
        self._client.loop_stop()
        self._client.disconnect()

    def _reap(self) -> None:
        """Tandai `failed` perintah yang tidak dijawab perangkat sampai batas waktu."""
        while not self._stop_evt.wait(0.5):
            for p in self.tracker.expired():
                try:
                    with SessionLocal() as db:
                        cmd = fail_unacked(
                            db, p.device_id, CommandAction(p.action),
                            settings.mqtt_ack_timeout_seconds,
                        )
                    if cmd is not None:
                        log.warning(
                            "perangkat %s tidak menjawab %s (cmd_id=%s): perintah #%s failed",
                            p.device_id, p.action, p.cmd_id, cmd.id,
                        )
                except Exception:
                    log.exception("gagal menandai perintah tanpa ack")

    # -- callback paho ------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            log.error("MQTT ditolak broker: %s", reason_code)
            return
        self.connected = True
        p = self.prefix
        for topic in (
            f"{p}/vision/+/occupancy",
            f"{p}/panel/+/event",
            f"{p}/panel/+/state",
            f"{p}/acunit/+/state",
        ):
            client.subscribe(topic, qos=1)
        client.publish(f"{p}/status/engine", "online", qos=1, retain=True)
        log.info("MQTT tersambung ke %s:%s", settings.mqtt_host, settings.mqtt_port)

    def _on_disconnect(self, client, userdata, flags, reason_code, properties) -> None:
        self.connected = False
        log.warning("MQTT terputus: %s", reason_code)

    def _on_message(self, client, userdata, msg) -> None:
        try:
            with SessionLocal() as db:
                handle_message(
                    db, self.prefix, msg.topic, msg.payload,
                    retained=bool(msg.retain), tracker=self.tracker,
                )
        except Exception:  # satu pesan buruk tidak boleh mematikan loop MQTT
            log.exception("gagal memproses %s", msg.topic)

    # -- keluar: perintah ke perangkat -------------------------------------
    def publish_command(self, device: Device, action: CommandAction) -> None:
        if not self.connected:
            raise DeviceError("broker MQTT belum tersambung")
        cmd_id = uuid.uuid4().hex[:12]
        payload = json.dumps(
            {"cmd_id": cmd_id, "action": action.value, "source": "engine"}
        )
        # Daftarkan sebelum publish: ack bisa tiba (di thread paho) sebelum publish() kembali.
        self.tracker.register(cmd_id, device.id, action.value)
        info = self._client.publish(f"{self.prefix}/cmd/{device.id}", payload, qos=1)
        if info.rc != mqtt.MQTT_ERR_SUCCESS:
            self.tracker.forget(cmd_id)
            raise DeviceError(f"publish MQTT gagal (rc={info.rc})")


class MqttDeviceAdapter:
    """DeviceAdapter yang mem-publish perintah lewat bridge."""

    def __init__(self, bridge: MqttBridge) -> None:
        self.bridge = bridge

    def send(self, device: Device, action: CommandAction) -> None:
        self.bridge.publish_command(device, action)


_bridge: MqttBridge | None = None


def get_bridge() -> MqttBridge | None:
    return _bridge


def start_bridge() -> MqttBridge:
    global _bridge
    _bridge = MqttBridge()
    _bridge.start()
    return _bridge


def stop_bridge() -> None:
    global _bridge
    if _bridge is not None:
        _bridge.stop()
        _bridge = None
