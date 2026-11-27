from datetime import date, timedelta, timezone

from sqlalchemy import func, select

from app.db.session import settings, utcnow
from app.models import DailyUsage, HourlyUsage, OccupancyRecord, Schedule
from app.services.usage_calendar_service import refresh_measured_usage, seed_dummy_daily_usage
from app.services.usage_overview_service import usage_overview


def test_usage_overview_totals_and_zero_previous_period(db, room):
    today = date.today()
    db.add(
        Schedule(
            room_id=room.id,
            day_of_week=today.weekday(),
            start_time="08:00",
            end_time="10:00",
            title="Kelas uji",
            active=True,
        )
    )
    db.add(
        DailyUsage(
            room_id=room.id,
            date=today,
            occupied_minutes=120,
            energy_kwh=3.25,
            idle_energy_kwh=1.2,
            idle_on_minutes=40,
            source="measured",
        )
    )
    db.commit()

    result = usage_overview(db, period="7d", today=today)

    assert result["current"]["totals"] == {
        "energy_kwh": 3.25,
        "occupied_hours": 2.0,
        "scheduled_hours": 2.0,
        "utilization_pct": 100.0,
        "idle_energy_kwh": 1.2,
        "idle_share_pct": 36.92,
    }
    assert result["previous"]["totals"]["energy_kwh"] == 0
    assert result["changes"]["energy_kwh_pct"] is None
    assert result["changes"]["utilization_pct"] is None
    assert len(result["current"]["series"]) == 7
    assert result["rooms"][0]["idle_energy_kwh"] == 1.2




def test_usage_overview_percent_changes_with_previous_values(db, room):
    today = date.today()
    db.add(
        Schedule(
            room_id=room.id,
            day_of_week=today.weekday(),
            start_time="08:00",
            end_time="10:00",
            title="Kelas uji",
            active=True,
        )
    )
    db.add_all(
        [
            DailyUsage(room_id=room.id, date=today, occupied_minutes=120, energy_kwh=3.25, idle_energy_kwh=1.2, source="dummy"),
            DailyUsage(room_id=room.id, date=today - timedelta(days=7), occupied_minutes=60, energy_kwh=2.0, idle_energy_kwh=0.4, source="dummy"),
        ]
    )
    db.commit()

    result = usage_overview(db, period="7d", today=today)

    assert result["changes"]["energy_kwh_pct"] == 62.5
    assert result["changes"]["occupied_hours_pct"] == 100.0
    assert result["changes"]["utilization_pct"] == 100.0
    assert result["changes"]["idle_energy_kwh_pct"] == 200.0


def test_usage_overview_utilization_is_null_without_schedule(db, room):
    today = date.today()
    db.add(
        DailyUsage(
            room_id=room.id,
            date=today,
            occupied_minutes=60,
            energy_kwh=1.0,
            idle_energy_kwh=0.2,
            source="dummy",
        )
    )
    db.commit()

    result = usage_overview(db, period="7d", today=today)

    assert result["current"]["totals"]["utilization_pct"] is None
    assert result["rooms"][0]["utilization_pct"] is None


def test_measured_idle_energy_requires_empty_interval_and_on_device(db, room, monkeypatch):
    monkeypatch.setattr(settings, "vision_stale_seconds", 60)
    now = utcnow()
    today = now.replace(tzinfo=timezone.utc).astimezone().date()
    first = now - timedelta(minutes=3)
    db.add_all(
        [
            OccupancyRecord(room_id=room.id, person_count=0, source="mqtt-vision", detected_at=first),
            OccupancyRecord(room_id=room.id, person_count=2, source="mqtt-vision", detected_at=first + timedelta(minutes=1)),
            OccupancyRecord(room_id=room.id, person_count=0, source="mqtt-vision", detected_at=first + timedelta(minutes=2)),
        ]
    )
    for device in room.devices:
        device.state = "off"
    db.commit()

    refresh_measured_usage(db, today, today, room_id=room.id)
    measured = db.scalars(
        select(DailyUsage).where(DailyUsage.room_id == room.id, DailyUsage.date == today)
    ).one()
    assert measured.source == "measured"
    assert measured.idle_on_minutes == 0
    assert measured.idle_energy_kwh == 0

    room.devices[0].state = "on"
    db.commit()
    refresh_measured_usage(db, today, today, room_id=room.id)
    db.refresh(measured)
    assert measured.idle_on_minutes == 2
    assert measured.idle_energy_kwh > 0
    assert measured.energy_kwh > measured.idle_energy_kwh
    assert measured.occupied_minutes == 1


def test_hour_heatmap_is_seven_by_24_and_levels_are_quartiles(db, room):
    today = date.today()
    values = [10, 20, 30, 40]
    for offset, value in enumerate(values):
        day = today - timedelta(days=offset)
        db.add(
            HourlyUsage(
                room_id=room.id,
                date=day,
                hour=10 + offset,
                occupied_minutes=value,
                energy_kwh=0.2,
            )
        )
    db.commit()

    result = usage_overview(db, period="7d", today=today)
    heatmap = result["hour_heatmap"]

    assert len(heatmap) == 7
    assert all(len(row) == 24 for row in heatmap)
    for offset, value in enumerate(values):
        day = today - timedelta(days=offset)
        cell = heatmap[day.weekday()][10 + offset]
        assert cell["average_occupied_minutes"] == value
        assert cell["level"] == offset + 1
    assert heatmap[0][0]["level"] == 0


def test_dummy_seed_profiles_are_deterministic_and_idempotent(db, room):
    today = date(2026, 10, 22)
    db.add(
        Schedule(
            room_id=room.id,
            day_of_week=0,
            start_time="08:00",
            end_time="12:00",
            title="Kelas contoh",
            active=True,
        )
    )
    db.commit()

    assert seed_dummy_daily_usage(db, today=today, weeks=1) == 7
    daily = db.scalars(select(DailyUsage).order_by(DailyUsage.date)).all()
    first_daily = [
        (row.date, row.occupied_minutes, row.energy_kwh, row.idle_on_minutes, row.idle_energy_kwh)
        for row in daily
    ]
    hourly = db.scalars(select(HourlyUsage).order_by(HourlyUsage.date, HourlyUsage.hour)).all()
    first_hourly = [
        (row.date, row.hour, row.occupied_minutes, row.energy_kwh)
        for row in hourly
    ]
    assert len(hourly) == 7 * 24
    assert all(row.source == "dummy" for row in daily)
    assert seed_dummy_daily_usage(db, today=today, weeks=1) == 0
    assert db.scalar(select(func.count(HourlyUsage.id))) == 7 * 24

    db.query(HourlyUsage).delete()
    db.query(DailyUsage).delete()
    db.commit()
    assert seed_dummy_daily_usage(db, today=today, weeks=1) == 7
    daily_again = db.scalars(select(DailyUsage).order_by(DailyUsage.date)).all()
    hourly_again = db.scalars(select(HourlyUsage).order_by(HourlyUsage.date, HourlyUsage.hour)).all()
    assert [
        (row.date, row.occupied_minutes, row.energy_kwh, row.idle_on_minutes, row.idle_energy_kwh)
        for row in daily_again
    ] == first_daily
    assert [
        (row.date, row.hour, row.occupied_minutes, row.energy_kwh)
        for row in hourly_again
    ] == first_hourly


def test_usage_overview_rejects_invalid_period(client, room):
    response = client.get("/dashboard/usage-overview?period=quarter")
    assert response.status_code == 422
