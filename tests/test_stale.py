"""Fail-safe kamera: data basi menjadi UNKNOWN dan mengulang jeda kosong."""
from app.models import Device, DeviceState
from app.schemas import OccupancyCreate
from app.services.event_service import (
    RoomOccupancyStatus,
    evaluate_rules,
    handle_occupancy,
    room_occupancy_status,
)


def _devices(db, room):
    return db.query(Device).filter(Device.room_id == room.id).order_by(Device.id).all()


def _zero(db, room, adapter, clock):
    _, commands = handle_occupancy(
        db,
        OccupancyCreate(room_id=room.id, person_count=0),
        adapter=adapter,
        live=True,
        clock=clock,
    )
    return commands


def test_kosong_19_detik_belum_off(db, room, adapter, clock):
    for index in range(4):  # t=0, 5, 10, 15
        assert _zero(db, room, adapter, clock) == []
        if index < 3:
            clock.advance(5)
    clock.advance(4)
    assert room_occupancy_status(db, room.id, now=clock()) == RoomOccupancyStatus.EMPTY_PENDING
    assert evaluate_rules(db, room.id, adapter=adapter, live=True, now=clock()) == []
    assert all(device.state == DeviceState.ON.value for device in _devices(db, room))


def test_kosong_berkelanjutan_20_detik_tepat_satu_off(db, room, adapter, clock):
    commands = []
    for _ in range(5):
        commands.extend(_zero(db, room, adapter, clock))
        clock.advance(5)
    assert len(commands) == 2
    assert all(command.action == "turn_off" for command in commands)
    assert _zero(db, room, adapter, clock) == []
    assert all(device.state == DeviceState.OFF.value for device in _devices(db, room))


def test_data_berhenti_unknown_tanpa_off_dan_timer_diulang_saat_pulih(db, room, adapter, clock):
    assert _zero(db, room, adapter, clock) == []
    clock.advance(7)
    assert room_occupancy_status(db, room.id, now=clock()) == RoomOccupancyStatus.UNKNOWN
    assert evaluate_rules(db, room.id, adapter=adapter, live=True, now=clock()) == []
    assert all(device.state == DeviceState.ON.value for device in _devices(db, room))

    # Pulih pada t=7. Pembacaan reguler menjaga stream tetap fresh.
    for index in range(4):  # t=7, 12, 17, 22
        assert _zero(db, room, adapter, clock) == []
        clock.advance(5)
    # Pada t=27, pembacaan terakhir masih segar dan nol sudah berlangsung 20 detik.
    assert room_occupancy_status(db, room.id, now=clock()) == RoomOccupancyStatus.EMPTY
    commands = _zero(db, room, adapter, clock)  # pesan berikutnya memicu evaluasi OFF
    assert len(commands) == 2
    assert room_occupancy_status(db, room.id, now=clock()) == RoomOccupancyStatus.EMPTY


def test_konfigurasi_empty_delay_dan_vision_stale_dibaca_dari_env(monkeypatch):
    from app.db.session import Settings

    monkeypatch.setenv("EMPTY_DELAY_SECONDS", "37")
    monkeypatch.setenv("VISION_STALE_SECONDS", "9")
    config = Settings(_env_file=None)
    assert config.empty_delay_seconds == 37
    assert config.vision_stale_seconds == 9
