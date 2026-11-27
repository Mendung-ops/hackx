"""Data kalender penggunaan demo dan agregasi pemakaian harian.

Layanan ini hanya membaca okupansi, jadwal, perintah, dan status perangkat;
tidak memanggil layanan kontrol dan tidak ikut menentukan perintah perangkat.
"""
from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
import hashlib
import random

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import settings, utcnow
from app.models import (
    Command,
    CommandAction,
    CommandStatus,
    DailyUsage,
    Device,
    DeviceState,
    HourlyUsage,
    OccupancyRecord,
    Room,
    Schedule,
)
from app.services.schedule_service import minutes

SYNTHETIC_OCCUPANCY_SOURCES = {"simulator", "test", "dummy", "dashboard"}
DEFAULT_WEEKS = 26


def date_range(start: date, end: date):
    current = start
    while current <= end:
        yield current
        current += timedelta(days=1)


def local_day_utc_bounds(day: date) -> tuple[datetime, datetime]:
    """Batas hari pada zona lokal server, dikembalikan sebagai UTC naive."""
    local_start = datetime.combine(day, time.min).astimezone()
    local_end = datetime.combine(day + timedelta(days=1), time.min).astimezone()
    return (
        local_start.astimezone(timezone.utc).replace(tzinfo=None),
        local_end.astimezone(timezone.utc).replace(tzinfo=None),
    )


def _local_date(timestamp: datetime) -> date:
    return timestamp.replace(tzinfo=timezone.utc).astimezone().date()


def _seed_number(room_id: int, day: date) -> int:
    return int.from_bytes(
        hashlib.sha256(f"smartx:{room_id}:{day.isoformat()}".encode()).digest()[:8],
        "big",
    )


def _allocate_integer(total: int, weights: list[float]) -> list[int]:
    if total <= 0:
        return [0] * len(weights)
    if not weights or sum(weights) <= 0:
        weights = [1.0 if 8 <= hour <= 17 else 0.0 for hour in range(len(weights))]
    weight_sum = sum(weights)
    exact = [total * weight / weight_sum for weight in weights]
    result = [int(value) for value in exact]
    remainder = total - sum(result)
    order = sorted(range(len(weights)), key=lambda i: (exact[i] - result[i], -i), reverse=True)
    for index in order[:remainder]:
        result[index] += 1
    return result


def _dummy_hour_profile(
    row: DailyUsage,
    room_schedules: list[Schedule],
    seed: int,
) -> list[tuple[int, float]]:
    rng = random.Random(seed ^ 0x5A17)
    scheduled_weights = [0.0] * 24
    for item in room_schedules:
        if item.day_of_week != row.date.weekday():
            continue
        start, end = minutes(item.start_time), minutes(item.end_time)
        for hour in range(24):
            scheduled_weights[hour] += max(0, min(end, hour * 60 + 60) - max(start, hour * 60))

    occupied_weights = scheduled_weights[:]
    if not any(occupied_weights):
        occupied_weights = [rng.uniform(0.4, 1.0) if 9 <= hour <= 15 else 0.0 for hour in range(24)]
    occupied = _allocate_integer(row.occupied_minutes, occupied_weights)

    idle_weights = [0.0] * 24
    if any(scheduled_weights):
        first = min((i for i, value in enumerate(scheduled_weights) if value), default=8)
        last = max((i for i, value in enumerate(scheduled_weights) if value), default=17)
        for hour in range(7, 20):
            idle_weights[hour] = 1.0 if hour < first or hour > last else 0.15
    else:
        idle_weights = [rng.uniform(0.2, 1.0) if 8 <= hour <= 18 else 0.0 for hour in range(24)]

    energy_weights = [occupied[hour] + idle_weights[hour] for hour in range(24)]
    if not any(energy_weights):
        energy_weights[12] = 1.0
    total_energy = max(0.0, float(row.energy_kwh or 0.0))
    weight_sum = sum(energy_weights)
    hourly_energy = [round(total_energy * weight / weight_sum, 6) for weight in energy_weights]
    if hourly_energy:
        hourly_energy[-1] = round(hourly_energy[-1] + total_energy - sum(hourly_energy), 6)
    return list(zip(occupied, hourly_energy, strict=True))


def seed_dummy_daily_usage(
    db: Session, *, today: date | None = None, weeks: int = DEFAULT_WEEKS
) -> int:
    """Isi tanggal yang belum punya riwayat dan lengkapi profil contoh secara idempoten."""
    today = today or date.today()
    start = today - timedelta(weeks=weeks)
    end = today - timedelta(days=1)
    rooms = db.scalars(select(Room).order_by(Room.id)).all()
    if not rooms or end < start:
        return 0

    room_ids = [room.id for room in rooms]
    rows = db.scalars(
        select(DailyUsage).where(
            DailyUsage.room_id.in_(room_ids),
            DailyUsage.date >= start,
            DailyUsage.date <= end,
        )
    ).all()
    by_key = {(row.room_id, row.date): row for row in rows}
    schedules = db.scalars(
        select(Schedule).where(Schedule.active.is_(True)).order_by(Schedule.room_id)
    ).all()
    schedules_by_room: dict[int, list[Schedule]] = {}
    for item in schedules:
        schedules_by_room.setdefault(item.room_id, []).append(item)
    watts = {
        room.id: sum(
            device.power_watt
            for device in db.scalars(
                select(Device).where(Device.room_id == room.id, Device.active.is_(True))
            ).all()
        )
        for room in rooms
    }
    effective_rooms = set(
        db.scalars(
            select(Device.room_id)
            .join(Command, Command.device_id == Device.id)
            .where(
                Command.status == CommandStatus.SENT.value,
                Command.action == CommandAction.TURN_OFF.value,
                Command.source == "rule",
            )
            .distinct()
        ).all()
    )

    created = 0
    for room in rooms:
        room_schedules = schedules_by_room.get(room.id, [])
        for day in date_range(start, end):
            key = (room.id, day)
            row = by_key.get(key)
            if row is None:
                rng = random.Random(_seed_number(room.id, day))
                sessions = [item for item in room_schedules if item.day_of_week == day.weekday()]
                scheduled_hours = sum(
                    (minutes(item.end_time) - minutes(item.start_time)) / 60
                    for item in sessions
                )
                holiday = day.weekday() < 5 and rng.random() < 0.035
                if holiday:
                    occupied_minutes, on_hours = 0, 0.0
                elif scheduled_hours:
                    occupied_minutes = round(scheduled_hours * rng.uniform(0.50, 0.95) * 60)
                    waste_hours = rng.uniform(0.08, min(0.6, max(0.08, scheduled_hours * 0.12)))
                    on_hours = occupied_minutes / 60 + waste_hours
                elif day.weekday() >= 5:
                    occupied_minutes = 0 if rng.random() < 0.8 else rng.randint(1, 18)
                    on_hours = occupied_minutes / 60 * rng.uniform(1.0, 1.5)
                else:
                    occupied_minutes, on_hours = 0, 0.0
                energy = watts[room.id] * on_hours / 1000 * rng.uniform(1.02, 1.15)
                row = DailyUsage(
                    room_id=room.id,
                    date=day,
                    occupied_minutes=occupied_minutes,
                    energy_kwh=round(energy, 4),
                    source="dummy",
                )
                db.add(row)
                db.flush()
                by_key[key] = row
                created += 1

            if row.source != "dummy":
                continue
            rng = random.Random(_seed_number(room.id, day) ^ 0xD00D)
            waste_share = rng.uniform(0.05, 0.13) if room.id in effective_rooms else rng.uniform(0.15, 0.25)
            row.idle_energy_kwh = round(row.energy_kwh * waste_share, 4)
            room_watts = max(watts[room.id], 1.0)
            row.idle_on_minutes = min(
                1440,
                round(row.idle_energy_kwh * 1000 / room_watts * 60),
            )

    dummy_rows = [row for row in by_key.values() if row.source == "dummy"]
    existing_hours = db.scalars(
        select(HourlyUsage).where(
            HourlyUsage.room_id.in_(room_ids),
            HourlyUsage.date >= start,
            HourlyUsage.date <= end,
        )
    ).all()
    hourly_by_key = {(row.room_id, row.date, row.hour): row for row in existing_hours}
    for row in dummy_rows:
        profile = _dummy_hour_profile(
            row, schedules_by_room.get(row.room_id, []), _seed_number(row.room_id, row.date)
        )
        for hour, (occupied_minutes, energy_kwh) in enumerate(profile):
            key = (row.room_id, row.date, hour)
            hourly = hourly_by_key.get(key)
            if hourly is None:
                hourly = HourlyUsage(room_id=row.room_id, date=row.date, hour=hour)
                db.add(hourly)
                hourly_by_key[key] = hourly
            hourly.occupied_minutes = occupied_minutes
            hourly.energy_kwh = energy_kwh
    db.commit()
    return created


def seed_dummy_daily_usage_if_empty(db: Session) -> int:
    # Seed juga melengkapi kolom dan profil per jam pada riwayat contoh versi lama.
    return seed_dummy_daily_usage(db)


def _local_hour_segments(start: datetime, end: datetime):
    """Pecah selang UTC-aware pada batas jam dinding lokal."""
    cursor = start
    while cursor < end:
        local = cursor.astimezone()
        next_local = local.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
        boundary = next_local.astimezone(timezone.utc)
        segment_end = min(end, boundary)
        if segment_end <= cursor:
            segment_end = min(end, cursor + timedelta(hours=1))
        yield local.date(), local.hour, (segment_end - cursor).total_seconds()
        cursor = segment_end


def _device_on_intervals(
    db: Session, device: Device, start: datetime, end: datetime
) -> list[tuple[datetime, datetime]]:
    commands = db.scalars(
        select(Command)
        .where(
            Command.device_id == device.id,
            Command.status == CommandStatus.SENT.value,
            Command.executed_at.is_not(None),
        )
        .order_by(Command.executed_at, Command.id)
    ).all()
    events = [
        (item.executed_at.replace(tzinfo=timezone.utc), item.action == CommandAction.TURN_ON.value)
        for item in commands
    ]
    before = [event for event in events if event[0] <= start]
    inside = [event for event in events if start < event[0] < end]
    if before:
        on = before[-1][1]
    elif events:
        on = not events[0][1]
    else:
        on = device.state == DeviceState.ON.value

    intervals: list[tuple[datetime, datetime]] = []
    cursor = start
    for timestamp, target_on in inside:
        if on and timestamp > cursor:
            intervals.append((cursor, timestamp))
        cursor = timestamp
        on = target_on
    if on and end > cursor:
        intervals.append((cursor, end))
    return intervals


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    merged: list[tuple[datetime, datetime]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1]:
            merged.append((start, end))
        elif end > merged[-1][1]:
            merged[-1] = (merged[-1][0], end)
    return merged


def _overlap_seconds(
    first: list[tuple[datetime, datetime]],
    second: list[tuple[datetime, datetime]],
):
    i = j = 0
    while i < len(first) and j < len(second):
        start = max(first[i][0], second[j][0])
        end = min(first[i][1], second[j][1])
        if end > start:
            yield start, end
        if first[i][1] <= second[j][1]:
            i += 1
        else:
            j += 1


def refresh_measured_usage(
    db: Session,
    start: date,
    end: date,
    *,
    room_id: int | None = None,
) -> int:
    """Perbarui tanggal dengan okupansi nyata dan energi dari timeline perangkat."""
    if end < start:
        return 0
    max_age = settings.vision_stale_seconds
    stale_delta = timedelta(seconds=max_age)
    start_naive, _ = local_day_utc_bounds(start)
    _, end_naive = local_day_utc_bounds(end)
    now_naive = utcnow()
    now = now_naive.replace(tzinfo=timezone.utc)
    range_start = start_naive.replace(tzinfo=timezone.utc)
    range_end = min(end_naive, now_naive).replace(tzinfo=timezone.utc)
    if range_end <= range_start:
        return 0

    stmt = (
        select(OccupancyRecord)
        .where(
            OccupancyRecord.detected_at >= start_naive - stale_delta,
            OccupancyRecord.detected_at <= min(end_naive + stale_delta, now_naive + stale_delta),
            OccupancyRecord.source.not_in(SYNTHETIC_OCCUPANCY_SOURCES),
        )
        .order_by(OccupancyRecord.room_id, OccupancyRecord.detected_at, OccupancyRecord.id)
    )
    if room_id is not None:
        stmt = stmt.where(OccupancyRecord.room_id == room_id)
    records = [record for record in db.scalars(stmt).all() if record.detected_at <= now_naive]
    if not records:
        return 0

    by_room: dict[int, list[OccupancyRecord]] = {}
    measured_days: set[tuple[int, date]] = set()
    occupied_seconds: dict[tuple[int, date], float] = {}
    occupied_by_hour: dict[tuple[int, date, int], float] = {}
    empty_intervals: dict[int, list[tuple[datetime, datetime]]] = {}
    for record in records:
        by_room.setdefault(record.room_id, []).append(record)
        record_day = _local_date(record.detected_at)
        if start <= record_day <= end:
            measured_days.add((record.room_id, record_day))

    for key_room, room_records in by_room.items():
        for index, record in enumerate(room_records):
            observed_start = record.detected_at.replace(tzinfo=timezone.utc)
            observed_end = (
                room_records[index + 1].detected_at.replace(tzinfo=timezone.utc)
                if index + 1 < len(room_records)
                else observed_start + stale_delta
            )
            observed_end = min(observed_end, observed_start + stale_delta, now, range_end)
            observed_start = max(observed_start, range_start)
            if observed_end <= observed_start:
                continue
            interval = (observed_start, observed_end)
            if record.person_count <= 0:
                empty_intervals.setdefault(key_room, []).append(interval)
            for day, hour, seconds in _local_hour_segments(*interval):
                if not start <= day <= end:
                    continue
                measured_days.add((key_room, day))
                key = (key_room, day)
                if record.person_count > 0:
                    occupied_seconds[key] = occupied_seconds.get(key, 0.0) + seconds
                    hour_key = (key_room, day, hour)
                    occupied_by_hour[hour_key] = occupied_by_hour.get(hour_key, 0.0) + seconds

    rooms_stmt = select(Room)
    if room_id is not None:
        rooms_stmt = rooms_stmt.where(Room.id == room_id)
    room_ids = {room.id for room in db.scalars(rooms_stmt).all()}
    devices_stmt = select(Device).where(Device.room_id.in_(room_ids)) if room_ids else select(Device).where(False)
    devices = db.scalars(devices_stmt).all()
    energy_by_hour: dict[tuple[int, date, int], float] = {}
    energy_by_day: dict[tuple[int, date], float] = {}
    idle_energy_by_day: dict[tuple[int, date], float] = {}
    on_intervals_by_room: dict[int, list[tuple[datetime, datetime]]] = {}
    for device in devices:
        intervals = _device_on_intervals(db, device, range_start, range_end)
        on_intervals_by_room.setdefault(device.room_id, []).extend(intervals)
        for interval in intervals:
            for day, hour, seconds in _local_hour_segments(*interval):
                if start <= day <= end:
                    key = (device.room_id, day, hour)
                    amount = device.power_watt * seconds / 3_600_000
                    energy_by_hour[key] = energy_by_hour.get(key, 0.0) + amount
                    day_key = (device.room_id, day)
                    energy_by_day[day_key] = energy_by_day.get(day_key, 0.0) + amount

        for on_start, on_end in _overlap_seconds(intervals, empty_intervals.get(device.room_id, [])):
            for day, _hour, seconds in _local_hour_segments(on_start, on_end):
                if start <= day <= end:
                    key = (device.room_id, day)
                    idle_energy_by_day[key] = (
                        idle_energy_by_day.get(key, 0.0) + device.power_watt * seconds / 3_600_000
                    )

    idle_on_seconds: dict[tuple[int, date], float] = {}
    for key_room, intervals in on_intervals_by_room.items():
        for on_start, on_end in _overlap_seconds(
            _merge_intervals(intervals), empty_intervals.get(key_room, [])
        ):
            for day, _hour, seconds in _local_hour_segments(on_start, on_end):
                if start <= day <= end:
                    key = (key_room, day)
                    idle_on_seconds[key] = idle_on_seconds.get(key, 0.0) + seconds

    daily_rows = db.scalars(
        select(DailyUsage).where(DailyUsage.date >= start, DailyUsage.date <= end)
    ).all()
    if room_id is not None:
        daily_rows = [row for row in daily_rows if row.room_id == room_id]
    daily_by_key = {(row.room_id, row.date): row for row in daily_rows}
    hourly_rows = db.scalars(
        select(HourlyUsage).where(HourlyUsage.date >= start, HourlyUsage.date <= end)
    ).all()
    if room_id is not None:
        hourly_rows = [row for row in hourly_rows if row.room_id == room_id]
    hourly_by_key = {(row.room_id, row.date, row.hour): row for row in hourly_rows}

    changed = 0
    for key_room, day in sorted(measured_days):
        if key_room not in room_ids:
            continue
        row = daily_by_key.get((key_room, day))
        if row is None:
            row = DailyUsage(room_id=key_room, date=day)
            db.add(row)
            daily_by_key[(key_room, day)] = row
        row.occupied_minutes = round(occupied_seconds.get((key_room, day), 0.0) / 60)
        row.energy_kwh = round(energy_by_day.get((key_room, day), 0.0), 4)
        row.idle_on_minutes = round(idle_on_seconds.get((key_room, day), 0.0) / 60)
        row.idle_energy_kwh = round(idle_energy_by_day.get((key_room, day), 0.0), 4)
        row.source = "measured"
        for hour in range(24):
            hour_key = (key_room, day, hour)
            hourly = hourly_by_key.get(hour_key)
            if hourly is None:
                hourly = HourlyUsage(room_id=key_room, date=day, hour=hour)
                db.add(hourly)
                hourly_by_key[hour_key] = hourly
            hourly.occupied_minutes = round(occupied_by_hour.get(hour_key, 0.0) / 60)
            hourly.energy_kwh = round(energy_by_hour.get(hour_key, 0.0), 6)
        changed += 1
    if changed:
        db.commit()
    return changed


def quartile_levels(values: list[float]) -> list[int]:
    """Level 0 untuk nol; nilai nonnol dibagi menurut kuartil nilai positif."""
    ordered = sorted(value for value in values if value > 0)
    if not ordered:
        return [0 for _ in values]
    if ordered[0] == ordered[-1]:
        return [4 if value > 0 else 0 for value in values]

    def percentile(fraction: float) -> float:
        position = (len(ordered) - 1) * fraction
        lower = int(position)
        upper = min(lower + 1, len(ordered) - 1)
        part = position - lower
        return ordered[lower] * (1 - part) + ordered[upper] * part

    q1, q2, q3 = (percentile(p) for p in (0.25, 0.5, 0.75))
    levels = []
    for value in values:
        if value <= 0:
            levels.append(0)
        elif value <= q1:
            levels.append(1)
        elif value <= q2:
            levels.append(2)
        elif value <= q3:
            levels.append(3)
        else:
            levels.append(4)
    return levels


def usage_calendar(
    db: Session,
    *,
    room_id: int | None = None,
    weeks: int = DEFAULT_WEEKS,
    metric: str = "occupancy",
    today: date | None = None,
) -> dict:
    today = today or date.today()
    start = today - timedelta(days=weeks * 7 - 1)
    refresh_measured_usage(db, start, today, room_id=room_id)

    stmt = select(DailyUsage).where(DailyUsage.date >= start, DailyUsage.date <= today)
    if room_id is not None:
        stmt = stmt.where(DailyUsage.room_id == room_id)
    rows = db.scalars(stmt).all()
    by_day: dict[date, list[DailyUsage]] = {}
    for row in rows:
        by_day.setdefault(row.date, []).append(row)

    schedules_stmt = select(Schedule).where(Schedule.active.is_(True))
    if room_id is not None:
        schedules_stmt = schedules_stmt.where(Schedule.room_id == room_id)
    schedules = db.scalars(schedules_stmt).all()
    schedules_by_weekday: dict[int, list[Schedule]] = {}
    for schedule in schedules:
        schedules_by_weekday.setdefault(schedule.day_of_week, []).append(schedule)

    raw: list[dict] = []
    for day in date_range(start, today):
        day_rows = by_day.get(day, [])
        occupied_hours = sum(row.occupied_minutes for row in day_rows) / 60
        energy_kwh = sum(row.energy_kwh for row in day_rows)
        sessions = schedules_by_weekday.get(day.weekday(), [])
        scheduled_hours = sum(
            (minutes(item.end_time) - minutes(item.start_time)) / 60
            for item in sessions
        )
        value = {
            "occupancy": occupied_hours,
            "energy": energy_kwh,
            "scheduled": scheduled_hours,
        }[metric]
        sources = {row.source for row in day_rows}
        source = "mixed" if len(sources) > 1 else next(iter(sources)) if sources else None
        raw.append(
            {
                "date": day,
                "value": value,
                "source": source,
                "occupied_hours": occupied_hours,
                "energy_kwh": energy_kwh,
                "scheduled_hours": scheduled_hours,
                "classes": len(sessions),
            }
        )

    levels = quartile_levels([item["value"] for item in raw])
    for item, level in zip(raw, levels, strict=True):
        item["level"] = level
        item["value"] = round(item["value"], 4)
        item["occupied_hours"] = round(item["occupied_hours"], 2)
        item["energy_kwh"] = round(item["energy_kwh"], 4)
        item["scheduled_hours"] = round(item["scheduled_hours"], 2)

    return {
        "metric": metric,
        "unit": {"occupancy": "jam", "energy": "kWh", "scheduled": "jam"}[metric],
        "from": start,
        "to": today,
        "days": raw,
    }
