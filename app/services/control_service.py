from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.adapters.device_adapter import DeviceAdapter, DeviceError, get_adapter
from app.db.session import settings, utcnow
from app.models import (
    Command,
    CommandAction,
    CommandSource,
    CommandStatus,
    Device,
    DeviceState,
)


class DeviceNotFound(LookupError):
    pass


class DeviceInactive(RuntimeError):
    """Perangkat dinonaktifkan di admin, perintah ditolak."""


class PhysicalLockActive(RuntimeError):
    """Rule engine dilarang mengirim OFF: tombol fisik baru saja ditekan."""


# Laporan LOCAL ganda (topic event + state) dalam jeda ini dianggap satu penekanan.
_LOCAL_DEDUPE = timedelta(seconds=2)


def local_lock_end(db: Session, device_id: int) -> datetime | None:
    """Kapan prioritas fisik berakhir (atau berakhir) untuk perangkat ini.

    Diturunkan dari riwayat perintah: perintah LOCAL turn_on terakhir yang
    berstatus sent, ditambah `local_lock_seconds`. Tanpa kolom baru di DB dan
    tetap utuh setelah server restart. None jika belum pernah ada.
    """
    last = db.scalars(
        select(Command)
        .where(
            Command.device_id == device_id,
            Command.source == CommandSource.LOCAL.value,
            Command.action == CommandAction.TURN_ON.value,
            Command.status == CommandStatus.SENT.value,
            Command.executed_at.is_not(None),
        )
        .order_by(Command.id.desc())
        .limit(1)
    ).first()
    if last is None:
        return None
    return last.executed_at + timedelta(seconds=settings.local_lock_seconds)


def is_locked(db: Session, device_id: int, now: datetime | None = None) -> bool:
    end = local_lock_end(db, device_id)
    return end is not None and (now or utcnow()) < end


def record_local_action(
    db: Session,
    device_id: int,
    action: CommandAction,
    now: datetime | None = None,
) -> Command:
    """Catat aksi tombol fisik (last_cmd_id=LOCAL). Perangkat sudah berubah sendiri,
    jadi tidak ada yang dikirim; yang dilakukan: catat jejak, sinkronkan state,
    dan (untuk turn_on) mulai jendela prioritas fisik.
    """
    device = db.get(Device, device_id)
    if device is None:
        raise DeviceNotFound(f"perangkat {device_id} tidak ditemukan")
    now = now or utcnow()

    last = db.scalars(
        select(Command)
        .where(
            Command.device_id == device_id,
            Command.source == CommandSource.LOCAL.value,
            Command.action == action.value,
        )
        .order_by(Command.id.desc())
        .limit(1)
    ).first()
    if last is not None and last.executed_at and now - last.executed_at < _LOCAL_DEDUPE:
        return last

    cmd = Command(
        device_id=device.id,
        action=action.value,
        source=CommandSource.LOCAL.value,
        status=CommandStatus.SENT.value,
        reason="tombol fisik (last_cmd_id=LOCAL)",
        executed_at=now,
    )
    device.state = _TARGET_STATE[action].value
    device.last_changed_at = now
    db.add(cmd)
    db.commit()
    db.refresh(cmd)
    return cmd


_TARGET_STATE = {
    CommandAction.TURN_ON: DeviceState.ON,
    CommandAction.TURN_OFF: DeviceState.OFF,
}


def fail_unacked(
    db: Session, device_id: int, action: CommandAction, timeout_s: float
) -> Command | None:
    """Perangkat tidak menjawab: tandai perintah `sent` terakhir sebagai `failed`.

    Konsisten dengan aturan `failed`: state perangkat dikembalikan ke keadaan
    sebelum perintah, sehingga aturan mencobanya lagi di pembacaan berikutnya.
    State tidak disentuh jika sudah berubah oleh laporan lain.
    """
    cmd = db.scalars(
        select(Command)
        .where(
            Command.device_id == device_id,
            Command.action == action.value,
            Command.status == CommandStatus.SENT.value,
            Command.source.in_([CommandSource.RULE.value, CommandSource.ENGINE.value, CommandSource.MANUAL.value]),
        )
        .order_by(Command.id.desc())
        .limit(1)
    ).first()
    if cmd is None:
        return None
    cmd.status = CommandStatus.FAILED.value
    cmd.reason = f"{cmd.reason or ''} | gagal: tidak ada ack dalam {timeout_s:g} dtk".strip(" |")[:255]
    device = db.get(Device, device_id)
    if device is not None and device.state == _TARGET_STATE[action].value:
        device.state = (
            DeviceState.OFF if action == CommandAction.TURN_ON else DeviceState.ON
        ).value
    db.commit()
    db.refresh(cmd)
    return cmd


def execute_command(
    db: Session,
    device_id: int,
    action: CommandAction,
    source: CommandSource = CommandSource.MANUAL,
    reason: str | None = None,
    *,
    adapter: DeviceAdapter | None = None,
    live: bool | None = None,
    now: datetime | None = None,
) -> Command:
    """Jalankan satu perintah ke perangkat dan catat jejaknya di tabel commands.

    live=False (default dari CONTROL_LIVE_MODE) -> dry-run: hanya dicatat,
    perangkat dan state-nya tidak disentuh.
    """
    device = db.get(Device, device_id)
    if device is None:
        raise DeviceNotFound(f"perangkat {device_id} tidak ditemukan")
    if not device.active:
        raise DeviceInactive(f"perangkat {device_id} nonaktif di admin")
    if (
        source == CommandSource.RULE
        and action == CommandAction.TURN_OFF
        and is_locked(db, device.id, now=now)
    ):
        # Pengaman terakhir; evaluate_rules sudah menyaring perangkat terkunci.
        raise PhysicalLockActive(
            f"perangkat {device_id} terkunci prioritas fisik, OFF dari rule ditolak"
        )
    live = settings.control_live_mode if live is None else live
    adapter = get_adapter() if adapter is None else adapter

    command_time = now or utcnow()
    cmd = Command(
        device_id=device.id,
        action=action.value,
        source=source.value,
        status=CommandStatus.PENDING.value,
        reason=reason,
        created_at=command_time,
    )
    db.add(cmd)
    db.flush()

    if not live:
        cmd.status = CommandStatus.DRY_RUN.value
    else:
        try:
            adapter.send(device, action)
        except DeviceError as exc:
            cmd.status = CommandStatus.FAILED.value
            cmd.reason = f"{reason or ''} | gagal: {exc}".strip(" |")[:255]
        else:
            cmd.status = CommandStatus.SENT.value
            cmd.executed_at = command_time
            device.state = _TARGET_STATE[action].value
            device.last_changed_at = command_time

    db.commit()
    db.refresh(cmd)
    return cmd
