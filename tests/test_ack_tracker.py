import json

from sqlalchemy import select

from app.models import Command, CommandAction, CommandSource, Device, DeviceState
from app.services.ack_tracker import AckTracker
from app.services.control_service import execute_command, fail_unacked
from app.services.mqtt_handler import handle_message


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


def _devices(db, room):
    return db.scalars(select(Device).where(Device.room_id == room.id).order_by(Device.id)).all()


def test_tracker_nonaktif_jika_timeout_nol():
    t = AckTracker(0)
    t.register("a", 1, "turn_off")
    assert not t.enabled and len(t) == 0


def test_ack_cocok_state_target_dan_hanya_sekali():
    t = AckTracker(10)
    t.register("a", 1, "turn_off")
    assert t.ack(1, "x", "on") is False  # state belum sesuai target
    assert t.ack(2, "a", "off") is False  # perangkat lain
    assert t.ack(1, "a", "off") is True
    assert t.ack(1, "a", "off") is False  # sudah ditutup
    assert len(t) == 0


def test_ack_tanpa_cmd_id_tetap_sah_lewat_state():
    t = AckTracker(10)
    t.register("a", 1, "turn_off")
    assert t.ack(1, "BOOT", "off") is True


def test_ack_memilih_cmd_id_yang_cocok_lebih_dulu():
    clock = FakeClock()
    t = AckTracker(10, clock=clock)
    t.register("a", 1, "turn_off")
    t.register("b", 1, "turn_off")
    assert t.ack(1, "b", "off") is True
    clock.t += 11
    assert [p.cmd_id for p in t.expired()] == ["a"]  # "a" tetap menunggu sampai lewat batas


def test_expired_hanya_yang_lewat_batas_dan_dihapus():
    clock = FakeClock()
    t = AckTracker(10, clock=clock)
    t.register("a", 1, "turn_off")
    clock.t += 5
    t.register("b", 2, "turn_on")
    clock.t += 6  # a: 11 dtk (lewat), b: 6 dtk
    assert [p.cmd_id for p in t.expired()] == ["a"]
    assert t.expired() == []
    clock.t += 5
    assert [p.cmd_id for p in t.expired()] == ["b"]


def test_forget_membuang_perintah():
    t = AckTracker(10)
    t.register("a", 1, "turn_off")
    t.forget("a")
    t.forget("tidak-ada")
    assert len(t) == 0


def test_fail_unacked_menandai_failed_dan_mengembalikan_state(db, room, adapter):
    lamp, _ = _devices(db, room)
    cmd = execute_command(
        db, lamp.id, CommandAction.TURN_OFF, CommandSource.RULE,
        reason="ruang kosong", adapter=adapter, live=True,
    )
    db.refresh(lamp)
    assert cmd.status == "sent" and lamp.state == DeviceState.OFF.value
    failed = fail_unacked(db, lamp.id, CommandAction.TURN_OFF, 10)
    db.refresh(lamp)
    assert failed.id == cmd.id and failed.status == "failed"
    assert "ruang kosong" in failed.reason and "tidak ada ack dalam 10 dtk" in failed.reason
    assert lamp.state == DeviceState.ON.value  # aturan akan mencoba lagi


def test_fail_unacked_tidak_menyentuh_state_yang_sudah_berubah(db, room, adapter):
    lamp, _ = _devices(db, room)
    execute_command(
        db, lamp.id, CommandAction.TURN_OFF, CommandSource.RULE, adapter=adapter, live=True
    )
    lamp.state = DeviceState.ON.value  # laporan lain sudah menyinkronkan state
    db.commit()
    fail_unacked(db, lamp.id, CommandAction.TURN_OFF, 10)
    db.refresh(lamp)
    assert lamp.state == DeviceState.ON.value


def test_fail_unacked_tanpa_perintah_sent_mengembalikan_none(db, room):
    lamp, _ = _devices(db, room)
    assert fail_unacked(db, lamp.id, CommandAction.TURN_OFF, 10) is None
    assert db.scalars(select(Command)).all() == []


def test_handler_state_cocok_menutup_perintah_tetapi_retained_tidak(db, room, adapter):
    lamp, _ = _devices(db, room)
    t = AckTracker(10)
    t.register("a", lamp.id, "turn_off")
    topic = f"smartx/panel/{lamp.id}/state"
    body = json.dumps({"state": "off", "last_cmd_id": "a"}).encode()
    handle_message(db, "smartx", topic, body, retained=True, adapter=adapter, tracker=t)
    assert len(t) == 1  # replay retained bukan ack
    handle_message(db, "smartx", topic, body, adapter=adapter, tracker=t)
    assert len(t) == 0
