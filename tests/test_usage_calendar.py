from datetime import date, timedelta, timezone

from sqlalchemy import select

from app.db.session import settings, utcnow
from app.models import DailyUsage, OccupancyRecord, Room, Schedule
from app.services.usage_calendar_service import quartile_levels, seed_dummy_daily_usage


def test_dummy_usage_seed_is_idempotent_and_deterministic(db, room):
    today = date(2026, 10, 22)
    db.add(
        Schedule(
            room_id=room.id,
            day_of_week=0,
            start_time="08:00",
            end_time="12:00",
            title="Pemrograman Web",
            active=True,
        )
    )
    db.commit()

    created = seed_dummy_daily_usage(db, today=today, weeks=2)
    first_rows = db.scalars(select(DailyUsage).order_by(DailyUsage.date)).all()
    first = [(row.date, row.occupied_minutes, row.energy_kwh) for row in first_rows]
    assert created == 14
    assert all(row.source == "dummy" for row in first_rows)
    assert seed_dummy_daily_usage(db, today=today, weeks=2) == 0

    db.query(DailyUsage).delete()
    db.commit()
    assert seed_dummy_daily_usage(db, today=today, weeks=2) == 14
    second_rows = db.scalars(select(DailyUsage).order_by(DailyUsage.date)).all()
    second = [(row.date, row.occupied_minutes, row.energy_kwh) for row in second_rows]
    assert second == first


def test_heatmap_quartiles_and_all_zero_values():
    assert quartile_levels([0, 0, 0]) == [0, 0, 0]
    assert quartile_levels([0, 1, 2, 3, 4]) == [0, 1, 2, 3, 4]
    assert quartile_levels([0, 2, 2]) == [0, 4, 4]


def test_usage_calendar_aggregates_all_rooms_and_filters_one(client, db, room):
    today = date.today()
    other = Room(name="Kelas T2")
    db.add(other)
    db.flush()
    db.add_all(
        [
            DailyUsage(room_id=room.id, date=today, occupied_minutes=120, energy_kwh=1.25, source="dummy"),
            DailyUsage(room_id=other.id, date=today, occupied_minutes=180, energy_kwh=2.5, source="dummy"),
        ]
    )
    db.commit()

    all_rooms = client.get("/dashboard/usage-calendar?weeks=1&metric=occupancy").json()
    one_room = client.get(
        f"/dashboard/usage-calendar?room_id={room.id}&weeks=1&metric=occupancy"
    ).json()
    all_today = next(item for item in all_rooms["days"] if item["date"] == today.isoformat())
    room_today = next(item for item in one_room["days"] if item["date"] == today.isoformat())
    assert all_rooms["from"] == (today - timedelta(days=6)).isoformat()
    assert all_today["value"] == 5.0 and all_today["energy_kwh"] == 3.75
    assert all_today["source"] == "dummy"
    assert room_today["value"] == 2.0 and room_today["energy_kwh"] == 1.25


def test_scheduled_metric_uses_active_room_schedules(client, db, room):
    today = date.today()
    db.add_all(
        [
            Schedule(room_id=room.id, day_of_week=today.weekday(), start_time="09:00", end_time="11:00", title="Kelas A", active=True),
            Schedule(room_id=room.id, day_of_week=today.weekday(), start_time="12:00", end_time="13:00", title="Kelas B", active=True),
            Schedule(room_id=room.id, day_of_week=today.weekday(), start_time="14:00", end_time="18:00", title="Nonaktif", active=False),
        ]
    )
    db.commit()

    response = client.get(
        f"/dashboard/usage-calendar?room_id={room.id}&weeks=1&metric=scheduled"
    )
    day = next(item for item in response.json()["days"] if item["date"] == today.isoformat())
    assert day["value"] == 3.0 and day["scheduled_hours"] == 3.0
    assert day["classes"] == 2


def test_measured_occupancy_replaces_dummy_row(client, db, room, monkeypatch):
    monkeypatch.setattr(settings, "vision_stale_seconds", 300)
    now = utcnow()
    today = now.replace(tzinfo=timezone.utc).astimezone().date()
    db.add(
        DailyUsage(
            room_id=room.id,
            date=today,
            occupied_minutes=300,
            energy_kwh=99,
            source="dummy",
        )
    )
    db.add_all(
        [
            OccupancyRecord(
                room_id=room.id,
                person_count=2,
                source="mqtt-vision",
                detected_at=now - timedelta(minutes=2),
            ),
            OccupancyRecord(
                room_id=room.id,
                person_count=0,
                source="mqtt-vision",
                detected_at=now - timedelta(seconds=1),
            ),
        ]
    )
    db.commit()

    response = client.get(
        f"/dashboard/usage-calendar?room_id={room.id}&weeks=1&metric=occupancy"
    )
    day = next(item for item in response.json()["days"] if item["date"] == today.isoformat())
    row = db.scalars(
        select(DailyUsage).where(DailyUsage.room_id == room.id, DailyUsage.date == today)
    ).one()
    assert row.source == "measured"
    assert 1 <= row.occupied_minutes <= 2
    assert row.energy_kwh < 99
    assert day["source"] == "measured" and day["occupied_hours"] < 0.1
