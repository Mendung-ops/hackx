from datetime import datetime, timedelta
from enum import Enum
from typing import Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.device_adapter import DeviceAdapter
from app.db.session import settings, utcnow
from app.models import (
    Command,
    CommandAction,
    CommandSource,
    CommandStatus,
    Device,
    DeviceState,
    DeviceType,
    OccupancyRecord,
    Room,
)
from app.schemas import OccupancyCreate
from app.services.control_service import execute_command, local_lock_end

Clock = Callable[[], datetime]


class RoomNotFound(LookupError):
    pass


class RoomOccupancyStatus(str, Enum):
    UNKNOWN = "unknown"
    OCCUPIED = "occupied"
    EMPTY_PENDING = "empty_pending"
    EMPTY = "empty"


def server_clock() -> datetime:
    """Waktu terima server dalam UTC naive, sesuai konvensi timestamp DB."""
    return utcnow()


def record_occupancy(
    db: Session,
    data: OccupancyCreate,
    *,
    received_at: datetime | None = None,
) -> OccupancyRecord:
    if db.get(Room, data.room_id) is None:
        raise RoomNotFound(f"ruang {data.room_id} tidak ditemukan")
    # Timestamp payload tidak dipercaya untuk keputusan kontrol; semua sumber memakai waktu terima server.
    record = OccupancyRecord(
        room_id=data.room_id,
        person_count=data.person_count,
        source=data.source,
        detected_at=received_at or server_clock(),
    )
    db.add(record)
    db.commit()
    db.refresh(record)
    return record


def room_occupancy_status(
    db: Session,
    room_id: int,
    *,
    now: datetime | None = None,
    since: datetime | None = None,
) -> RoomOccupancyStatus:
    """Nilai kondisi dari waktu terima server dan deret pembacaan ruang.

    UNKNOWN berlaku jika belum ada data atau pembacaan terbaru lebih tua dari
    `VISION_STALE_SECONDS`. EMPTY hanya berlaku jika nol berlangsung sekurangnya
    `EMPTY_DELAY_SECONDS`, dengan celah antarpembacaan tidak melebihi ambang stale.
    ``since`` membatasi deret, misalnya setelah akhir kunci tombol fisik.
    """
    now = now or server_clock()
    stale_after = timedelta(seconds=settings.vision_stale_seconds)
    latest = db.scalars(
        select(OccupancyRecord)
        .where(OccupancyRecord.room_id == room_id)
        .order_by(OccupancyRecord.detected_at.desc(), OccupancyRecord.id.desc())
        .limit(1)
    ).first()
    if latest is None or now - latest.detected_at > stale_after:
        return RoomOccupancyStatus.UNKNOWN
    if since is not None and latest.detected_at <= since:
        return RoomOccupancyStatus.EMPTY_PENDING
    if latest.person_count > 0:
        return RoomOccupancyStatus.OCCUPIED

    delay = timedelta(seconds=settings.empty_delay_seconds)
    cutoff = now - delay
    if since is not None and since > cutoff:
        cutoff = since

    recent_stmt = select(OccupancyRecord).where(
        OccupancyRecord.room_id == room_id,
        OccupancyRecord.detected_at >= cutoff,
    )
    if since is not None:
        recent_stmt = recent_stmt.where(OccupancyRecord.detected_at > since)
    recent = list(db.scalars(
        recent_stmt.order_by(OccupancyRecord.detected_at.desc(), OccupancyRecord.id.desc())
    ).all())

    # Satu pembacaan sebelum jendela diperlukan untuk mendeteksi celah stale tepat di batas.
    previous_stmt = select(OccupancyRecord).where(
        OccupancyRecord.room_id == room_id,
        OccupancyRecord.detected_at < cutoff,
    )
    if since is not None:
        previous_stmt = previous_stmt.where(OccupancyRecord.detected_at > since)
    previous = db.scalars(
        previous_stmt.order_by(OccupancyRecord.detected_at.desc(), OccupancyRecord.id.desc()).limit(1)
    ).first()
    if previous is not None:
        recent.append(previous)

    if not recent:
        return RoomOccupancyStatus.EMPTY_PENDING

    newer = recent[0]
    empty_since = newer.detected_at
    for older in recent[1:]:
        gap = newer.detected_at - older.detected_at
        if gap > stale_after or older.person_count != 0:
            break
        empty_since = older.detected_at
        newer = older

    if now - empty_since >= delay:
        return RoomOccupancyStatus.EMPTY
    return RoomOccupancyStatus.EMPTY_PENDING


def _occupied_since(db: Session, room_id: int, now: datetime) -> datetime | None:
    """Awal deret okupansi terkonfirmasi yang masih segar, atau None bila belum cukup."""
    threshold = settings.on_min_persons
    delay = timedelta(seconds=settings.on_delay_seconds)
    stale_after = timedelta(seconds=settings.vision_stale_seconds)
    latest = db.scalars(
        select(OccupancyRecord)
        .where(OccupancyRecord.room_id == room_id)
        .order_by(OccupancyRecord.detected_at.desc(), OccupancyRecord.id.desc())
        .limit(1)
    ).first()
    if (
        latest is None
        or now - latest.detected_at > stale_after
        or latest.person_count < threshold
    ):
        return None
    if delay.total_seconds() == 0:
        return latest.detected_at

    cutoff = now - delay
    recent = list(db.scalars(
        select(OccupancyRecord)
        .where(
            OccupancyRecord.room_id == room_id,
            OccupancyRecord.detected_at >= cutoff,
        )
        .order_by(OccupancyRecord.detected_at.desc(), OccupancyRecord.id.desc())
    ).all())
    previous = db.scalars(
        select(OccupancyRecord)
        .where(
            OccupancyRecord.room_id == room_id,
            OccupancyRecord.detected_at < cutoff,
        )
        .order_by(OccupancyRecord.detected_at.desc(), OccupancyRecord.id.desc())
        .limit(1)
    ).first()
    if previous is not None:
        recent.append(previous)
    if not recent:
        return None

    newer = recent[0]
    occupied_since = newer.detected_at
    for older in recent[1:]:
        if (
            newer.detected_at - older.detected_at > stale_after
            or older.person_count < threshold
        ):
            break
        occupied_since = older.detected_at
        newer = older
    return occupied_since if now - occupied_since >= delay else None


def _already_requested_on(db: Session, device_id: int, now: datetime) -> bool:
    """Cegah duplikasi ON: dry-run idempoten, publish sukses punya cooldown stale."""
    last = db.scalars(
        select(Command)
        .where(Command.device_id == device_id)
        .order_by(Command.id.desc())
        .limit(1)
    ).first()
    if last is None or last.source != CommandSource.ENGINE.value or last.action != CommandAction.TURN_ON.value:
        return False
    if last.status == CommandStatus.DRY_RUN.value:
        last_attempt_at = last.created_at
    elif last.status == CommandStatus.SENT.value:
        last_attempt_at = last.executed_at
    else:
        return False
    return (
        last_attempt_at is not None
        and now - last_attempt_at <= timedelta(seconds=settings.vision_stale_seconds)
    )


def _already_requested_off(db: Session, device_id: int) -> bool:
    """Hindari perintah dry-run yang sama menumpuk di setiap pembacaan."""
    last = db.scalars(
        select(Command)
        .where(Command.device_id == device_id)
        .order_by(Command.id.desc())
        .limit(1)
    ).first()
    return (
        last is not None
        and last.action == CommandAction.TURN_OFF.value
        and last.status == CommandStatus.DRY_RUN.value
    )


def evaluate_rules(
    db: Session,
    room_id: int,
    *,
    adapter: DeviceAdapter | None = None,
    live: bool | None = None,
    now: datetime | None = None,
) -> list[Command]:
    """Jalankan aturan ON terkonfirmasi dan OFF ruang kosong.

    Data yang UNKNOWN tidak memicu kontrol. Kunci fisik tetap membatasi OFF dari
    rule; ON otomatis berlaku untuk perangkat light dan ac yang belum menyala.
    """
    now = now or server_clock()
    devices = db.scalars(
        select(Device).where(
            Device.room_id == room_id,
            Device.state == DeviceState.ON.value,
            Device.active.is_(True),
        )
    ).all()
    reason = f"ruang kosong ≥{settings.empty_delay_seconds:g} detik (deteksi nol berkelanjutan)"
    commands: list[Command] = []
    for device in devices:
        lock_end = local_lock_end(db, device.id)
        if lock_end is not None and now < lock_end:
            continue
        if room_occupancy_status(db, room_id, now=now, since=lock_end) != RoomOccupancyStatus.EMPTY:
            continue
        if _already_requested_off(db, device.id):
            continue
        commands.append(
            execute_command(
                db,
                device.id,
                CommandAction.TURN_OFF,
                CommandSource.RULE,
                reason,
                adapter=adapter,
                live=live,
                now=now,
            )
        )

    occupied_since = _occupied_since(db, room_id, now)
    if occupied_since is not None:
        on_reason = (
            f"okupansi ≥{settings.on_min_persons} orang berkelanjutan "
            f"≥{settings.on_delay_seconds:g} detik"
        )
        devices_to_turn_on = db.scalars(
            select(Device).where(
                Device.room_id == room_id,
                Device.active.is_(True),
                Device.state != DeviceState.ON.value,
                Device.type.in_([DeviceType.LIGHT.value, DeviceType.AC.value]),
            )
        ).all()
        for device in devices_to_turn_on:
            if _already_requested_on(db, device.id, now):
                continue
            commands.append(
                execute_command(
                    db,
                    device.id,
                    CommandAction.TURN_ON,
                    CommandSource.ENGINE,
                    on_reason,
                    adapter=adapter,
                    live=live,
                    now=now,
                )
            )
    return commands


def handle_occupancy(
    db: Session,
    data: OccupancyCreate,
    *,
    adapter: DeviceAdapter | None = None,
    live: bool | None = None,
    clock: Clock | None = None,
) -> tuple[OccupancyRecord, list[Command]]:
    """Simpan pembacaan pada waktu terima lalu evaluasi aturan ruang."""
    received_at = (clock or server_clock)()
    record = record_occupancy(db, data, received_at=received_at)
    commands = evaluate_rules(db, data.room_id, adapter=adapter, live=live, now=received_at)
    return record, commands
