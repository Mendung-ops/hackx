import pytest
from sqlalchemy import select

from app.adapters.device_adapter import SimulatedDeviceAdapter
from app.models import Command, CommandAction, CommandSource, CommandStatus, Device, DeviceState
from app.schemas import OccupancyCreate
from app.services.control_service import DeviceNotFound, execute_command
from app.services.event_service import RoomNotFound, handle_occupancy


def _devices(db, room):
    return db.scalars(select(Device).where(Device.room_id == room.id).order_by(Device.id)).all()


def _feed(db, room, counts, *, clock, step_seconds=5, **kw):
    last = []
    for c in counts:
        _, last = handle_occupancy(db, OccupancyCreate(room_id=room.id, person_count=c), clock=clock, **kw)
        clock.advance(step_seconds)
    return last


# --- execute_command -------------------------------------------------------

def test_dry_run_mencatat_tanpa_mengubah_state(db, room, adapter):
    dev = _devices(db, room)[0]
    cmd = execute_command(db, dev.id, CommandAction.TURN_OFF, adapter=adapter, live=False)
    assert cmd.status == CommandStatus.DRY_RUN.value
    assert cmd.executed_at is None
    assert dev.state == DeviceState.ON.value
    assert adapter.sent == []


def test_live_mengubah_state_dan_mengirim_ke_adapter(db, room, adapter):
    dev = _devices(db, room)[0]
    cmd = execute_command(db, dev.id, CommandAction.TURN_OFF, adapter=adapter, live=True)
    assert cmd.status == CommandStatus.SENT.value
    assert cmd.executed_at is not None
    assert dev.state == DeviceState.OFF.value
    assert adapter.sent == [(dev.id, "turn_off")]


def test_adapter_gagal_dicatat_dan_state_tidak_berubah(db, room):
    dev = _devices(db, room)[0]
    bad = SimulatedDeviceAdapter(fail_device_ids={dev.id})
    cmd = execute_command(db, dev.id, CommandAction.TURN_OFF, adapter=bad, live=True, reason="uji")
    assert cmd.status == CommandStatus.FAILED.value
    assert "gagal" in cmd.reason
    assert dev.state == DeviceState.ON.value


def test_perangkat_tidak_ada(db):
    with pytest.raises(DeviceNotFound):
        execute_command(db, 999, CommandAction.TURN_ON, live=False)


# --- aturan ruang kosong ---------------------------------------------------

def test_belum_kosong_sebelum_jeda_20_detik(db, room, adapter, clock):
    cmds = _feed(db, room, [0] * 4, clock=clock, adapter=adapter, live=True)
    assert cmds == []
    assert all(d.state == DeviceState.ON.value for d in _devices(db, room))


def test_kosong_20_detik_mematikan_semua_perangkat(db, room, adapter, clock):
    cmds = _feed(db, room, [0] * 5, clock=clock, adapter=adapter, live=True)
    assert len(cmds) == 2
    assert all(c.source == CommandSource.RULE.value for c in cmds)
    assert all(d.state == DeviceState.OFF.value for d in _devices(db, room))


def test_ada_orang_di_tengah_mereset_jeda(db, room, adapter, clock):
    cmds = _feed(db, room, [0, 0, 3, 0, 0], clock=clock, adapter=adapter, live=True)
    assert cmds == []
    assert all(d.state == DeviceState.ON.value for d in _devices(db, room))


def test_dry_run_tidak_menumpuk_perintah(db, room, adapter, clock):
    _feed(db, room, [0] * 6, clock=clock, adapter=adapter, live=False)
    jumlah = len(db.scalars(select(Command)).all())
    assert jumlah == 2  # satu per perangkat, bukan per pembacaan


def test_perangkat_yang_sudah_mati_tidak_dikirimi_perintah(db, room, adapter, clock):
    _feed(db, room, [0] * 5, clock=clock, adapter=adapter, live=True)
    cmds = _feed(db, room, [0], clock=clock, adapter=adapter, live=True)
    assert cmds == []


def test_ruang_tidak_ada(db):
    with pytest.raises(RoomNotFound):
        handle_occupancy(db, OccupancyCreate(room_id=999, person_count=1), live=False)


def test_flicker_0_0_1_0_0_tidak_mematikan(db, room, adapter, clock):
    cmds = _feed(db, room, [0, 0, 1, 0, 0], clock=clock, step_seconds=3, adapter=adapter, live=True)
    assert cmds == []
    assert all(device.state == DeviceState.ON.value for device in _devices(db, room))
