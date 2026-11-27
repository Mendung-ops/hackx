import json
from datetime import timedelta

from sqlalchemy import select

from app.db.session import utcnow
from app.models import Command, Device, DeviceState, OccupancyRecord
from app.services.control_service import is_locked
from app.services.mqtt_handler import handle_message, parse_topic

P = "smartx"


def _devices(db, room):
    lamp, ac = db.scalars(
        select(Device).where(Device.room_id == room.id).order_by(Device.id)
    ).all()
    return lamp, ac


def _msg(db, topic, payload, adapter, **kw):
    return handle_message(
        db, P, topic, json.dumps(payload).encode(), adapter=adapter, live=True, **kw
    )


def test_parse_topic():
    assert parse_topic(P, "smartx/panel/3/event") == ("panel", 3, "event")
    assert parse_topic(P, "smartx/vision/1/occupancy") == ("vision", 1, "occupancy")
    assert parse_topic(P, "lain/panel/3/event") is None
    assert parse_topic(P, "smartx/panel/x/event") is None
    assert parse_topic(P, "smartx/status/engine") is None


def test_ts_dari_perangkat_diabaikan_dan_diberi_cap_waktu_terima(db, room, adapter):
    before = utcnow()
    _msg(
        db,
        f"smartx/vision/{room.id}/occupancy",
        {"person_count": 3, "ts": "2001-01-01T00:00:00"},
        adapter,
    )
    rec = db.scalars(select(OccupancyRecord)).one()
    assert rec.source == "mqtt-vision"
    assert before - timedelta(seconds=1) <= rec.detected_at <= utcnow()


def test_nol_20_detik_mematikan_perangkat_lewat_adapter(db, room, adapter, clock):
    lamp, ac = _devices(db, room)
    for _ in range(5):
        _msg(db, f"smartx/vision/{room.id}/occupancy", {"person_count": 0}, adapter, now=clock())
        clock.advance(5)
    assert {(lamp.id, "turn_off"), (ac.id, "turn_off")} == set(adapter.sent)


def test_tombol_dosen_local_mengunci_lampu(db, room, adapter, clock):
    lamp, ac = _devices(db, room)
    cmds = _msg(
        db,
        f"smartx/panel/{lamp.id}/event",
        {"action": "turn_on", "last_cmd_id": "LOCAL"},
        adapter,
        now=clock(),
    )
    assert cmds[0].source == "local" and is_locked(db, lamp.id, now=clock())
    for _ in range(5):
        _msg(db, f"smartx/vision/{room.id}/occupancy", {"person_count": 0}, adapter, now=clock())
        clock.advance(5)
    assert (lamp.id, "turn_off") not in adapter.sent
    assert (ac.id, "turn_off") in adapter.sent


def test_event_tanpa_local_diabaikan(db, room, adapter):
    lamp, _ = _devices(db, room)
    cmds = _msg(
        db, f"smartx/panel/{lamp.id}/event", {"action": "turn_on", "last_cmd_id": "abc"}, adapter
    )
    assert cmds == [] and not is_locked(db, lamp.id)


def test_event_local_retained_tidak_memulai_lock(db, room, adapter):
    lamp, _ = _devices(db, room)
    # replay retained saat backend reconnect: bukan penekanan tombol baru
    cmds = _msg(
        db, f"smartx/panel/{lamp.id}/event",
        {"action": "turn_on", "last_cmd_id": "LOCAL"}, adapter, retained=True,
    )
    assert cmds == [] and not is_locked(db, lamp.id)
    assert db.scalars(select(Command)).all() == []
    # penekanan nyata (bukan retained) tetap mengunci
    _msg(db, f"smartx/panel/{lamp.id}/event", {"action": "turn_on", "last_cmd_id": "LOCAL"}, adapter)
    assert is_locked(db, lamp.id)


def test_state_local_non_retained_ikut_mengunci_tapi_retained_tidak(db, room, adapter):
    lamp, ac = _devices(db, room)
    # replay retained saat reconnect: hanya sinkron state, tanpa lock baru
    _msg(
        db, f"smartx/panel/{lamp.id}/state", {"state": "off", "last_cmd_id": "LOCAL"},
        adapter, retained=True,
    )
    db.refresh(lamp)
    assert lamp.state == DeviceState.OFF.value and not is_locked(db, lamp.id)
    assert db.scalars(select(Command)).all() == []
    # laporan baru (bukan retained) dari tombol fisik: lock dimulai
    _msg(db, f"smartx/panel/{lamp.id}/state", {"state": "on", "last_cmd_id": "LOCAL"}, adapter)
    assert is_locked(db, lamp.id)


def test_state_acunit_menyinkronkan_state(db, room, adapter):
    _, ac = _devices(db, room)
    _msg(db, f"smartx/acunit/{ac.id}/state", {"state": "off", "last_cmd_id": "abc123"}, adapter)
    db.refresh(ac)
    assert ac.state == DeviceState.OFF.value


def test_pesan_rusak_atau_id_tak_dikenal_tidak_melempar(db, room, adapter):
    assert handle_message(db, P, f"smartx/vision/{room.id}/occupancy", b"bukan json") == []
    assert _msg(db, "smartx/vision/999/occupancy", {"person_count": 0}, adapter) == []
    assert _msg(db, "smartx/panel/999/event", {"last_cmd_id": "LOCAL"}, adapter) == []
    assert _msg(db, f"smartx/vision/{room.id}/occupancy", {"person_count": -1}, adapter) == []
    assert _msg(db, f"smartx/vision/{room.id}/occupancy", {"person_count": True}, adapter) == []
