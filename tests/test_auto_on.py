from sqlalchemy import select

from app.db.session import Settings, settings
from app.models import Command, CommandAction, CommandSource, Device, DeviceState, DeviceType
from app.schemas import OccupancyCreate
from app.services.event_service import RoomOccupancyStatus, handle_occupancy, room_occupancy_status


def _devices(db, room):
    return db.scalars(select(Device).where(Device.room_id == room.id).order_by(Device.id)).all()


def _occupancy(db, room, adapter, clock, count, *, live=True):
    return handle_occupancy(
        db,
        OccupancyCreate(room_id=room.id, person_count=count),
        adapter=adapter,
        live=live,
        clock=clock,
    )[1]


def _turn_off_all(db, room):
    for device in _devices(db, room):
        device.state = DeviceState.OFF.value
    db.commit()


def test_okupansi_terkonfirmasi_menyalakan_light_dan_ac_tepat_sekali(db, room, adapter, clock, monkeypatch):
    monkeypatch.setattr(settings, "on_min_persons", 1)
    monkeypatch.setattr(settings, "on_delay_seconds", 2.0)
    _turn_off_all(db, room)

    assert _occupancy(db, room, adapter, clock, 1) == []
    clock.advance(1)
    assert _occupancy(db, room, adapter, clock, 1) == []
    clock.advance(1)
    commands = _occupancy(db, room, adapter, clock, 1)

    assert len(commands) == 2
    assert {command.action for command in commands} == {CommandAction.TURN_ON.value}
    assert {command.source for command in commands} == {CommandSource.ENGINE.value}
    assert {device.type for device in _devices(db, room)} == {DeviceType.LIGHT.value, DeviceType.AC.value}
    assert _occupancy(db, room, adapter, clock, 1) == []
    assert len(db.scalars(select(Command).where(Command.source == CommandSource.ENGINE.value)).all()) == 2


def test_deteksi_singkat_lalu_nol_tidak_memicu_on(db, room, adapter, clock, monkeypatch):
    monkeypatch.setattr(settings, "on_min_persons", 1)
    monkeypatch.setattr(settings, "on_delay_seconds", 2.0)
    _turn_off_all(db, room)

    assert _occupancy(db, room, adapter, clock, 1) == []
    clock.advance(1)
    assert _occupancy(db, room, adapter, clock, 1) == []
    clock.advance(0.5)
    assert _occupancy(db, room, adapter, clock, 0) == []
    assert all(device.state == DeviceState.OFF.value for device in _devices(db, room))


def test_perangkat_yang_sudah_on_tidak_dikirimi_on_lagi(db, room, adapter, clock, monkeypatch):
    monkeypatch.setattr(settings, "on_min_persons", 1)
    monkeypatch.setattr(settings, "on_delay_seconds", 2.0)
    devices = _devices(db, room)
    devices[0].state = DeviceState.ON.value
    devices[1].state = DeviceState.OFF.value
    db.commit()

    assert _occupancy(db, room, adapter, clock, 1) == []
    clock.advance(2)
    commands = _occupancy(db, room, adapter, clock, 1)
    assert [command.device_id for command in commands] == [devices[1].id]


def test_unknown_tidak_menyalakan_perangkat(db, room, adapter, clock, monkeypatch):
    monkeypatch.setattr(settings, "on_min_persons", 1)
    monkeypatch.setattr(settings, "on_delay_seconds", 2.0)
    _turn_off_all(db, room)
    assert _occupancy(db, room, adapter, clock, 1) == []
    clock.advance(7)

    assert room_occupancy_status(db, room.id, now=clock()) == RoomOccupancyStatus.UNKNOWN
    assert _occupancy(db, room, adapter, clock, 1) == []
    assert all(device.state == DeviceState.OFF.value for device in _devices(db, room))


def test_delay_nol_menyalakan_pada_pembacaan_pertama(db, room, adapter, clock, monkeypatch):
    monkeypatch.setattr(settings, "on_min_persons", 1)
    monkeypatch.setattr(settings, "on_delay_seconds", 0.0)
    _turn_off_all(db, room)

    commands = _occupancy(db, room, adapter, clock, 1)
    assert len(commands) == 2
    assert all(command.action == CommandAction.TURN_ON.value for command in commands)


def test_ambang_orang_diterapkan_pada_auto_on(db, room, adapter, clock, monkeypatch):
    monkeypatch.setattr(settings, "on_min_persons", 2)
    monkeypatch.setattr(settings, "on_delay_seconds", 0.0)
    _turn_off_all(db, room)

    assert _occupancy(db, room, adapter, clock, 1) == []
    assert len(_occupancy(db, room, adapter, clock, 2)) == 2


def test_konfigurasi_auto_on_dibaca_dari_env(monkeypatch):
    monkeypatch.setenv("ON_MIN_PERSONS", "3")
    monkeypatch.setenv("ON_DELAY_SECONDS", "4.5")
    config = Settings(_env_file=None)
    assert config.on_min_persons == 3
    assert config.on_delay_seconds == 4.5


def test_perintah_engine_dry_run_tidak_spam(db, room, adapter, clock, monkeypatch):
    monkeypatch.setattr(settings, "on_min_persons", 1)
    monkeypatch.setattr(settings, "on_delay_seconds", 0.0)
    _turn_off_all(db, room)

    assert len(_occupancy(db, room, adapter, clock, 1, live=False)) == 2
    clock.advance(1)
    assert _occupancy(db, room, adapter, clock, 1, live=False) == []
    assert len(db.scalars(select(Command).where(Command.source == CommandSource.ENGINE.value)).all()) == 2


def test_source_engine_tidak_bisa_dipilih_via_api(client, admin_headers, room):
    response = client.post(
        "/commands",
        json={"device_id": 1, "action": "turn_on", "source": "engine"},
        headers=admin_headers,
    )
    assert response.status_code == 422
