from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db, settings
from app.models import DeviceState, OccupancyRecord, Room
from app.schemas.usage_calendar import UsageCalendarRead, UsageMetric
from app.schemas.usage_overview import UsageOverviewPeriodName, UsageOverviewRead
from app.schemas import (
    DashboardOverview,
    DeviceEnergy,
    DeviceRead,
    EnergySummary,
    RoomOverview,
    RoomRead,
)
from app.services import energy_service
from app.services.usage_calendar_service import usage_calendar
from app.services.usage_overview_service import usage_overview

router = APIRouter(prefix="/dashboard", tags=["dashboard"])


@router.get("/overview", response_model=DashboardOverview)
def overview(db: Session = Depends(get_db)):
    """Ringkasan semua ruang: perangkat, okupansi terakhir, dan daya saat ini."""
    rooms = db.scalars(select(Room).order_by(Room.id)).all()
    items: list[RoomOverview] = []
    for room in rooms:
        latest = db.scalars(
            select(OccupancyRecord)
            .where(OccupancyRecord.room_id == room.id)
            .order_by(OccupancyRecord.detected_at.desc(), OccupancyRecord.id.desc())
            .limit(1)
        ).first()
        active = [d for d in room.devices if d.active]
        on = [d for d in active if d.state == DeviceState.ON.value]
        items.append(
            RoomOverview(
                room=RoomRead.model_validate(room),
                devices=[DeviceRead.model_validate(d) for d in active],
                latest_person_count=latest.person_count if latest else None,
                last_detected_at=latest.detected_at if latest else None,
                devices_on=len(on),
                power_watt_now=sum(d.power_watt for d in on),
            )
        )
    return DashboardOverview(
        live_mode=settings.control_live_mode,
        total_devices_on=sum(i.devices_on for i in items),
        total_power_watt_now=sum(i.power_watt_now for i in items),
        rooms=items,
    )


def _naive_utc(dt: datetime | None) -> datetime | None:
    if dt is not None and dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


@router.get("/energy", response_model=EnergySummary)
def energy(
    start: datetime | None = None,
    end: datetime | None = None,
    room_id: int | None = None,
    db: Session = Depends(get_db),
):
    """Energi (kWh), emisi karbon (kgCO2), dan estimasi penghematan.

    Default jendela: 24 jam terakhir. Penghematan hanya dihitung dari perintah
    otomatis (`rule`) berstatus `sent`.
    """
    try:
        result = energy_service.summarize(
            db, _naive_utc(start), _naive_utc(end), room_id
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc))

    devices = [
        DeviceEnergy(
            device_id=i.device.id,
            device_name=i.device.name,
            room_id=i.device.room_id,
            type=i.device.type,
            power_watt=i.device.power_watt,
            on_hours=round(i.on_hours, 4),
            energy_kwh=round(i.energy_kwh, 4),
            saved_kwh=round(i.saved_kwh, 4),
            co2_kg=round(energy_service.co2_kg(i.energy_kwh), 4),
            saved_co2_kg=round(energy_service.co2_kg(i.saved_kwh), 4),
        )
        for i in result.items
    ]
    total_kwh = sum(i.energy_kwh for i in result.items)
    total_saved = sum(i.saved_kwh for i in result.items)
    return EnergySummary(
        start=result.start,
        end=result.end,
        live_mode=settings.control_live_mode,
        emission_factor_kg_per_kwh=settings.emission_factor_kg_per_kwh,
        emission_factor_source=settings.emission_factor_source,
        total_energy_kwh=round(total_kwh, 4),
        total_saved_kwh=round(total_saved, 4),
        total_co2_kg=round(energy_service.co2_kg(total_kwh), 4),
        total_saved_co2_kg=round(energy_service.co2_kg(total_saved), 4),
        devices=devices,
    )


@router.get("/usage-overview", response_model=UsageOverviewRead)
def usage_overview_endpoint(
    period: UsageOverviewPeriodName = "7d",
    db: Session = Depends(get_db),
):
    """Ringkasan historis seluruh ruang untuk tampilan; tidak dipakai rule engine."""
    return usage_overview(db, period=period)


@router.get("/usage-calendar", response_model=UsageCalendarRead)
def usage_calendar_endpoint(
    room_id: int | None = None,
    weeks: int = Query(default=26, ge=1, le=52),
    metric: UsageMetric = "occupancy",
    db: Session = Depends(get_db),
):
    """Riwayat kalender untuk rekomendasi UI; tidak dipakai aturan kontrol."""
    return usage_calendar(db, room_id=room_id, weeks=weeks, metric=metric)
