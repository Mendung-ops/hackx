"""Agregasi ringkasan penggunaan lintas ruang untuk tampilan dashboard."""
from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import DailyUsage, HourlyUsage, Room, Schedule
from app.services.schedule_service import minutes
from app.services.usage_calendar_service import (
    date_range,
    quartile_levels,
    refresh_measured_usage,
)


PERIOD_DAYS = {"7d": 7, "30d": 30, "6m": 182}


def _pct_change(current: float | None, previous: float | None) -> float | None:
    if current is None or previous is None or previous == 0:
        return None
    return round((current - previous) / previous * 100, 2)


def _utilization(occupied_hours: float, scheduled_hours: float) -> float | None:
    if scheduled_hours <= 0:
        return None
    return round(occupied_hours / scheduled_hours * 100, 2)


def _share(idle_energy: float, energy: float) -> float | None:
    if energy <= 0:
        return None
    return round(idle_energy / energy * 100, 2)


def _period_values(
    start: date,
    end: date,
    *,
    period: str,
    rooms: list[Room],
    daily_by_key: dict[tuple[int, date], DailyUsage],
    schedules_by_weekday: dict[tuple[int, int], list[Schedule]],
) -> tuple[dict, dict[int, dict[str, float | None]]]:
    room_totals: dict[int, dict[str, float | None]] = {
        room.id: {
            "energy_kwh": 0.0,
            "occupied_hours": 0.0,
            "scheduled_hours": 0.0,
            "idle_energy_kwh": 0.0,
        }
        for room in rooms
    }
    bucket_values: dict[date, dict[str, float]] = {}
    for day in date_range(start, end):
        bucket_date = day if period != "6m" else max(start, day - timedelta(days=day.weekday()))
        values = bucket_values.setdefault(
            bucket_date,
            {"energy_kwh": 0.0, "idle_energy_kwh": 0.0},
        )
        for room in rooms:
            row = daily_by_key.get((room.id, day))
            occupied_hours = row.occupied_minutes / 60 if row else 0.0
            energy_kwh = float(row.energy_kwh or 0.0) if row else 0.0
            idle_energy = float(row.idle_energy_kwh or 0.0) if row else 0.0
            sessions = schedules_by_weekday.get((room.id, day.weekday()), [])
            scheduled_hours = sum(
                (minutes(item.end_time) - minutes(item.start_time)) / 60
                for item in sessions
            )
            totals = room_totals[room.id]
            totals["energy_kwh"] += energy_kwh
            totals["occupied_hours"] += occupied_hours
            totals["scheduled_hours"] += scheduled_hours
            totals["idle_energy_kwh"] += idle_energy
            values["energy_kwh"] += energy_kwh
            values["idle_energy_kwh"] += idle_energy

    total_energy = sum(float(row["energy_kwh"] or 0) for row in room_totals.values())
    total_occupied = sum(float(row["occupied_hours"] or 0) for row in room_totals.values())
    total_scheduled = sum(float(row["scheduled_hours"] or 0) for row in room_totals.values())
    total_idle = sum(float(row["idle_energy_kwh"] or 0) for row in room_totals.values())
    totals = {
        "energy_kwh": round(total_energy, 4),
        "occupied_hours": round(total_occupied, 2),
        "scheduled_hours": round(total_scheduled, 2),
        "utilization_pct": _utilization(total_occupied, total_scheduled),
        "idle_energy_kwh": round(total_idle, 4),
        "idle_share_pct": _share(total_idle, total_energy),
    }
    series = [
        {
            "date": bucket,
            "energy_kwh": round(values["energy_kwh"], 4),
            "idle_energy_kwh": round(values["idle_energy_kwh"], 4),
        }
        for bucket, values in sorted(bucket_values.items())
    ]
    for values in room_totals.values():
        values["energy_kwh"] = round(float(values["energy_kwh"] or 0), 4)
        values["occupied_hours"] = round(float(values["occupied_hours"] or 0), 2)
        values["scheduled_hours"] = round(float(values["scheduled_hours"] or 0), 2)
        values["utilization_pct"] = _utilization(
            float(values["occupied_hours"] or 0),
            float(values["scheduled_hours"] or 0),
        )
        values["idle_energy_kwh"] = round(float(values["idle_energy_kwh"] or 0), 4)
    return {"from": start, "to": end, "totals": totals, "series": series}, room_totals


def usage_overview(
    db: Session,
    *,
    period: str = "7d",
    today: date | None = None,
) -> dict:
    today = today or date.today()
    days = PERIOD_DAYS[period]
    current_start = today - timedelta(days=days - 1)
    previous_end = current_start - timedelta(days=1)
    previous_start = previous_end - timedelta(days=days - 1)

    refresh_measured_usage(db, previous_start, today)
    rooms = db.scalars(select(Room).order_by(Room.id)).all()
    schedules = db.scalars(select(Schedule).where(Schedule.active.is_(True))).all()
    schedules_by_weekday: dict[tuple[int, int], list[Schedule]] = {}
    for item in schedules:
        schedules_by_weekday.setdefault((item.room_id, item.day_of_week), []).append(item)

    daily_rows = db.scalars(
        select(DailyUsage).where(
            DailyUsage.date >= previous_start,
            DailyUsage.date <= today,
        )
    ).all()
    daily_by_key = {(row.room_id, row.date): row for row in daily_rows}
    current, room_totals = _period_values(
        current_start,
        today,
        period=period,
        rooms=rooms,
        daily_by_key=daily_by_key,
        schedules_by_weekday=schedules_by_weekday,
    )
    previous, _ = _period_values(
        previous_start,
        previous_end,
        period=period,
        rooms=rooms,
        daily_by_key=daily_by_key,
        schedules_by_weekday=schedules_by_weekday,
    )

    current_totals = current["totals"]
    previous_totals = previous["totals"]
    changes = {
        "energy_kwh_pct": _pct_change(current_totals["energy_kwh"], previous_totals["energy_kwh"]),
        "occupied_hours_pct": _pct_change(current_totals["occupied_hours"], previous_totals["occupied_hours"]),
        "utilization_pct": _pct_change(current_totals["utilization_pct"], previous_totals["utilization_pct"]),
        "idle_energy_kwh_pct": _pct_change(current_totals["idle_energy_kwh"], previous_totals["idle_energy_kwh"]),
        "idle_share_pct": _pct_change(current_totals["idle_share_pct"], previous_totals["idle_share_pct"]),
    }
    room_results = [
        {"room_id": room.id, "name": room.name, **room_totals[room.id]}
        for room in rooms
    ]

    hourly_rows = db.scalars(
        select(HourlyUsage).where(
            HourlyUsage.date >= current_start,
            HourlyUsage.date <= today,
        )
    ).all()
    weekday_counts = {weekday: 0 for weekday in range(7)}
    for day in date_range(current_start, today):
        weekday_counts[day.weekday()] += 1
    hourly_sums = [[0.0 for _hour in range(24)] for _weekday in range(7)]
    for row in hourly_rows:
        hourly_sums[row.date.weekday()][row.hour] += row.occupied_minutes
    divisor_rooms = max(len(rooms), 1)
    raw_heat = [
        [
            round(
                hourly_sums[weekday][hour]
                / max(weekday_counts[weekday] * divisor_rooms, 1),
                2,
            )
            for hour in range(24)
        ]
        for weekday in range(7)
    ]
    levels = quartile_levels([value for row in raw_heat for value in row])
    hour_heatmap = []
    level_index = 0
    for weekday in range(7):
        cells = []
        for hour in range(24):
            cells.append(
                {
                    "average_occupied_minutes": raw_heat[weekday][hour],
                    "level": levels[level_index],
                }
            )
            level_index += 1
        hour_heatmap.append(cells)

    return {
        "period": period,
        "current": current,
        "previous": previous,
        "changes": changes,
        "rooms": room_results,
        "hour_heatmap": hour_heatmap,
        "has_dummy": any(
            row.source == "dummy"
            for row in daily_rows
            if previous_start <= row.date <= today
        ),
    }
