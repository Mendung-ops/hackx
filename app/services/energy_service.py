"""Hitung energi (kWh), emisi karbon (kgCO2), dan estimasi penghematan.

Dasarnya riwayat perintah berstatus `sent` di tabel commands: tiap perintah
mengubah perangkat jadi ON/OFF pada `executed_at`, dan daya perangkat dianggap
konstan (`power_watt`) saat ON.

Asumsi penting:
- Keadaan perangkat SEBELUM perintah pertama tidak tercatat, jadi ditebak:
  kebalikan dari target perintah pertama (turn_off -> tadinya ON). Tanpa
  perintah sama sekali, dipakai state perangkat saat ini.
- Penghematan = lamanya perangkat mati setelah perintah `rule` turn_off
  (sampai ada perintah berikutnya), dibandingkan andai perangkat tetap
  menyala. Ini estimasi, bukan hasil ukur.
- Mode dry-run tidak mengubah perangkat, jadi tidak menghasilkan penghematan.
"""
from dataclasses import dataclass
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import settings, utcnow
from app.models import (
    Command,
    CommandAction,
    CommandSource,
    CommandStatus,
    Device,
    DeviceState,
)

DEFAULT_WINDOW = timedelta(hours=24)

# (waktu, target_on, oleh_rule)
Event = tuple[datetime, bool, bool]


@dataclass
class DeviceEnergyResult:
    device: Device
    on_hours: float
    energy_kwh: float
    saved_kwh: float


@dataclass
class EnergyResult:
    start: datetime
    end: datetime
    items: list[DeviceEnergyResult]


def co2_kg(kwh: float, factor: float | None = None) -> float:
    factor = settings.emission_factor_kg_per_kwh if factor is None else factor
    return kwh * factor


def integrate(
    events: list[Event], current_on: bool, start: datetime, end: datetime
) -> tuple[float, float]:
    """Kembalikan (jam menyala, jam mati karena rule) dalam jendela [start, end]."""
    if end <= start:
        return 0.0, 0.0

    before = [e for e in events if e[0] <= start]
    inside = [e for e in events if start < e[0] < end]
    if before:
        _, on, by_rule = before[-1]
        rule_off = (not on) and by_rule
    elif events:
        on, rule_off = (not events[0][1]), False
    else:
        on, rule_off = current_on, False

    on_s = saved_s = 0.0
    cursor = start
    for t, target_on, by_rule in [*inside, (end, on, False)]:
        seconds = (t - cursor).total_seconds()
        if on:
            on_s += seconds
        elif rule_off:
            saved_s += seconds
        cursor = t
        if target_on:
            rule_off = False
        elif on:
            rule_off = by_rule
        on = target_on
    return on_s / 3600, saved_s / 3600


def _events_for(db: Session, device_id: int) -> list[Event]:
    cmds = db.scalars(
        select(Command)
        .where(
            Command.device_id == device_id,
            Command.status == CommandStatus.SENT.value,
            Command.executed_at.is_not(None),
        )
        .order_by(Command.executed_at, Command.id)
    ).all()
    return [
        (
            c.executed_at,
            c.action == CommandAction.TURN_ON.value,
            c.source == CommandSource.RULE.value,
        )
        for c in cmds
    ]


def summarize(
    db: Session,
    start: datetime | None = None,
    end: datetime | None = None,
    room_id: int | None = None,
) -> EnergyResult:
    now = utcnow()
    end = min(end or now, now)
    start = start or (end - DEFAULT_WINDOW)
    if start >= end:
        raise ValueError("start harus lebih awal dari end (dan end tidak boleh di masa depan)")

    stmt = select(Device).order_by(Device.id)
    if room_id is not None:
        stmt = stmt.where(Device.room_id == room_id)

    items: list[DeviceEnergyResult] = []
    for device in db.scalars(stmt).all():
        on_hours, saved_hours = integrate(
            _events_for(db, device.id),
            device.state == DeviceState.ON.value,
            start,
            end,
        )
        items.append(
            DeviceEnergyResult(
                device=device,
                on_hours=on_hours,
                energy_kwh=device.power_watt * on_hours / 1000,
                saved_kwh=device.power_watt * saved_hours / 1000,
            )
        )
    return EnergyResult(start=start, end=end, items=items)
