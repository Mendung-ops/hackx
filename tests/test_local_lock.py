from datetime import timedelta

import pytest
from sqlalchemy import select

from app.db.session import settings, utcnow
from app.models import (
    Command,
    CommandAction,
    CommandSource,
    Device,
    DeviceState,
    OccupancyRecord,
)
from app.schemas import OccupancyCreate
from app.services.control_service import (
    PhysicalLockActive,
    execute_command,
    is_locked,
    local_lock_end,
    record_local_action,
)
from app.services.event_service import handle_occupancy


def _devices(db, room):
    lamp, ac = db.scalars(
        select(Device).where(Device.room_id == room.id).order_by(Device.id)
    ).all()
    return lamp, ac


def _zeros(db, room, adapter, clock, n=5, step_seconds=5):
    cmds = []
    for _ in range(n):
        _, c = handle_occupancy(
            db, OccupancyCreate(room_id=room.id, person_count=0), adapter=adapter, live=True, clock=clock
        )
        cmds += c
        clock.advance(step_seconds)
    return cmds


def test_lock_dimulai_dari_tombol_fisik(db, room, clock):
    lamp, _ = _devices(db, room)
    assert local_lock_end(db, lamp.id) is None
    cmd = record_local_action(db, lamp.id, CommandAction.TURN_ON, now=clock())
    assert cmd.source == CommandSource.LOCAL.value and cmd.status == "sent"
    assert is_locked(db, lamp.id, now=clock())
    assert local_lock_end(db, lamp.id) == cmd.executed_at + timedelta(
        seconds=settings.local_lock_seconds
    )


def test_tidak_kirim_off_selama_lock(db, room, adapter, clock):
    lamp, ac = _devices(db, room)
    record_local_action(db, lamp.id, CommandAction.TURN_ON, now=clock())
    cmds = _zeros(db, room, adapter, clock, n=5)
    assert [c.device_id for c in cmds] == [ac.id]  # hanya AC yang tidak terkunci
    assert (lamp.id, "turn_off") not in adapter.sent
    db.refresh(lamp)
    assert lamp.state == DeviceState.ON.value


def test_jeda_kosong_dimulai_setelah_lock_berakhir(db, room, adapter, clock):
    lamp, ac = _devices(db, room)
    # Lock dimulai pada jam uji. Nol sebelum dan tepat di batas akhir lock tidak dihitung.
    record_local_action(db, lamp.id, CommandAction.TURN_ON, now=clock())
    for _ in range(25):  # t=0..120 dtk
        handle_occupancy(
            db, OccupancyCreate(room_id=room.id, person_count=0), adapter=adapter, live=True, clock=clock
        )
        clock.advance(5)
    assert lamp.state == DeviceState.ON.value

    # Pembacaan pertama setelah lock memulai jeda 20 detik yang baru.
    _zeros(db, room, adapter, clock, n=4, step_seconds=5)
    assert lamp.state == DeviceState.ON.value
    _, commands = handle_occupancy(
        db, OccupancyCreate(room_id=room.id, person_count=0), adapter=adapter, live=True, clock=clock
    )
    assert lamp.id in [command.device_id for command in commands]


def test_pengaman_execute_command_menolak_off_rule(db, room, adapter):
    lamp, _ = _devices(db, room)
    record_local_action(db, lamp.id, CommandAction.TURN_ON)
    with pytest.raises(PhysicalLockActive):
        execute_command(
            db, lamp.id, CommandAction.TURN_OFF, CommandSource.RULE, adapter=adapter, live=True
        )
    # perintah manual dari dashboard tetap diizinkan
    cmd = execute_command(
        db, lamp.id, CommandAction.TURN_OFF, CommandSource.MANUAL, adapter=adapter, live=True
    )
    assert cmd.status == "sent"


def test_tekan_ganda_dalam_2_detik_dihitung_satu(db, room):
    lamp, _ = _devices(db, room)
    a = record_local_action(db, lamp.id, CommandAction.TURN_ON)
    b = record_local_action(db, lamp.id, CommandAction.TURN_ON)
    assert a.id == b.id
    assert len(db.scalars(select(Command)).all()) == 1


def test_api_source_local_ditolak_dan_off_rule_saat_lock_409(client, db, room, admin_headers):
    lamp, _ = _devices(db, room)
    r = client.post(
        "/commands",
        json={"device_id": lamp.id, "action": "turn_off", "source": "local"},
        headers=admin_headers,
    )
    assert r.status_code == 422
    record_local_action(db, lamp.id, CommandAction.TURN_ON)
    r = client.post(
        "/commands",
        json={"device_id": lamp.id, "action": "turn_off", "source": "rule"},
        headers=admin_headers,
    )
    assert r.status_code == 409
