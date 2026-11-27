"""Terjemahkan pesan MQTT menjadi aksi di rule engine (tanpa ketergantungan ke broker).

Topik (prefix default `smartx`, lihat docs/mqtt-contract.md):
    {p}/vision/{room_id}/occupancy      {"person_count": 2}
    {p}/panel/{device_id}/event         {"action": "turn_on", "last_cmd_id": "LOCAL"}
    {p}/panel|acunit/{device_id}/state  {"state": "on", "last_cmd_id": "<id>|LOCAL"}

Cap waktu: ESP32 tidak punya NTP, jadi field `ts` di payload DIABAIKAN. Semua
waktu (detected_at, executed_at, last_changed_at) adalah waktu terima di server.
"""
import json
import logging
from datetime import datetime

from sqlalchemy.orm import Session

from app.adapters.device_adapter import DeviceAdapter
from app.db.session import utcnow
from app.models import Command, CommandAction, Device, DeviceState
from app.schemas import OccupancyCreate
from app.services.ack_tracker import AckTracker
from app.services.control_service import DeviceNotFound, record_local_action
from app.services.event_service import RoomNotFound, handle_occupancy

log = logging.getLogger("hackx.mqtt")

LOCAL_ID = "LOCAL"


def parse_topic(prefix: str, topic: str) -> tuple[str, int, str] | None:
    """`smartx/panel/3/event` -> ("panel", 3, "event"); None jika bukan topik kita."""
    parts = topic.split("/")
    if len(parts) != 4 or parts[0] != prefix or not parts[2].isdigit():
        return None
    return parts[1], int(parts[2]), parts[3]


def _json(payload: bytes) -> dict | None:
    try:
        data = json.loads(payload)
    except (ValueError, UnicodeDecodeError):
        return None
    return data if isinstance(data, dict) else None


def handle_message(
    db: Session,
    prefix: str,
    topic: str,
    payload: bytes,
    *,
    retained: bool = False,
    now: datetime | None = None,
    adapter: DeviceAdapter | None = None,
    live: bool | None = None,
    tracker: AckTracker | None = None,
) -> list[Command]:
    """Proses satu pesan. Mengembalikan perintah yang dihasilkan (jejak di tabel
    commands). Pesan rusak atau untuk id yang tidak dikenal dicatat lalu diabaikan."""
    parsed = parse_topic(prefix, topic)
    data = _json(payload)
    if parsed is None or data is None:
        log.warning("pesan diabaikan: topic=%s payload=%r", topic, payload[:80])
        return []
    kind, ident, leaf = parsed
    now = now or utcnow()

    try:
        if kind == "vision" and leaf == "occupancy":
            count = data.get("person_count", data.get("count"))
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                log.warning("person_count tidak valid: %r", data)
                return []
            # detected_at sengaja None -> waktu terima server
            _, cmds = handle_occupancy(
                db,
                OccupancyCreate(room_id=ident, person_count=count, source="mqtt-vision"),
                adapter=adapter,
                live=live,
                clock=lambda: now,
            )
            return cmds

        if kind == "panel" and leaf == "event":
            if data.get("last_cmd_id") != LOCAL_ID:
                return []
            # Event retained = replay saat reconnect, bukan penekanan baru:
            # tidak boleh memulai lock (sama seperti topik state).
            if retained:
                log.info("event retained diabaikan: topic=%s", topic)
                return []
            action = CommandAction.TURN_OFF if data.get("action") == "turn_off" else CommandAction.TURN_ON
            return [record_local_action(db, ident, action, now)]

        if kind in ("panel", "acunit") and leaf == "state":
            state = data.get("state")
            if state not in (DeviceState.ON.value, DeviceState.OFF.value):
                return []
            # Pesan retained (replay saat reconnect) tidak boleh memulai lock baru.
            if data.get("last_cmd_id") == LOCAL_ID and not retained:
                action = CommandAction.TURN_ON if state == "on" else CommandAction.TURN_OFF
                return [record_local_action(db, ident, action, now)]
            device = db.get(Device, ident)
            if device is None:
                raise DeviceNotFound(f"perangkat {ident} tidak ditemukan")
            # Laporan state baru (bukan replay retained) yang cocok dengan perintah
            # menunggu = ack dari perangkat.
            if tracker is not None and not retained:
                if tracker.ack(ident, data.get("last_cmd_id"), state):
                    log.info("ack perangkat %s: state=%s", ident, state)
            if device.state != state:
                device.state = state
                device.last_changed_at = now
                db.commit()
            return []
    except (RoomNotFound, DeviceNotFound) as exc:
        log.warning("id tidak dikenal, pesan diabaikan: %s", exc)
        return []

    log.warning("topik tidak dikenal: %s", topic)
    return []
