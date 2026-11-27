"""Layanan data jadwal; tidak terhubung ke mesin aturan perangkat."""
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import Room, Schedule


def minutes(value: str) -> int:
    hour, minute = value.split(":", 1)
    return int(hour) * 60 + int(minute)


def find_conflict(
    db: Session,
    *,
    room_id: int,
    day_of_week: int,
    start_time: str,
    end_time: str,
    exclude_id: int | None = None,
) -> Schedule | None:
    if minutes(end_time) <= minutes(start_time):
        return None
    stmt = select(Schedule).where(
        Schedule.room_id == room_id,
        Schedule.day_of_week == day_of_week,
        Schedule.active.is_(True),
    )
    if exclude_id is not None:
        stmt = stmt.where(Schedule.id != exclude_id)
    start, end = minutes(start_time), minutes(end_time)
    return next(
        (
            item
            for item in db.scalars(stmt).all()
            if start < minutes(item.end_time) and end > minutes(item.start_time)
        ),
        None,
    )


def sample_specs(db: Session) -> list[tuple[int, int, str, str, str]]:
    rooms = db.scalars(select(Room).order_by(Room.id)).all()
    if not rooms:
        return []

    definitions = {
        "A101": [
            (0, "08:00", "12:00", "Pemrograman Web"),
            (2, "08:00", "12:00", "Pemrograman Web"),
            (4, "08:00", "12:00", "Pemrograman Web"),
            (1, "13:00", "17:30", "Basis Data"),
            (3, "13:00", "17:30", "Basis Data"),
        ],
        "A102": [
            (day, "09:00", "11:00", "Jaringan Komputer")
            for day in range(4)
        ],
        "A103": [
            (day, "15:00", "18:00", "Sistem Cerdas")
            for day in (1, 3)
        ],
    }
    result: list[tuple[int, int, str, str, str]] = []
    for fallback_index, (room_code, entries) in enumerate(definitions.items()):
        room = next((r for r in rooms if room_code.casefold() in r.name.casefold()), None)
        if room is None and fallback_index < len(rooms):
            room = rooms[fallback_index]
        if room is None:
            continue
        result.extend((room.id, *entry) for entry in entries)
    return result


def seed_sample_schedules(db: Session) -> dict[str, int]:
    """Isi jadwal contoh yang belum ada; pertahankan jadwal buatan admin."""
    created = skipped_conflicts = 0
    for room_id, day, start, end, title in sample_specs(db):
        exact = db.scalars(
            select(Schedule).where(
                Schedule.room_id == room_id,
                Schedule.day_of_week == day,
                Schedule.start_time == start,
                Schedule.end_time == end,
                Schedule.title == title,
            )
        ).first()
        if exact is not None:
            continue
        conflict = find_conflict(
            db,
            room_id=room_id,
            day_of_week=day,
            start_time=start,
            end_time=end,
        )
        if conflict is not None:
            skipped_conflicts += 1
            continue
        db.add(
            Schedule(
                room_id=room_id,
                day_of_week=day,
                start_time=start,
                end_time=end,
                title=title,
                active=True,
            )
        )
        db.flush()
        created += 1
    db.commit()
    return {"created": created, "skipped_conflicts": skipped_conflicts}


def seed_sample_schedules_if_empty(db: Session) -> dict[str, int]:
    count = db.scalar(select(func.count(Schedule.id))) or 0
    if count:
        return {"created": 0, "skipped_conflicts": 0}
    return seed_sample_schedules(db)
