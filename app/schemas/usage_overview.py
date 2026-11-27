from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


UsageOverviewPeriodName = Literal["7d", "30d", "6m"]


class UsageOverviewTotals(BaseModel):
    energy_kwh: float
    occupied_hours: float
    scheduled_hours: float
    utilization_pct: float | None
    idle_energy_kwh: float
    idle_share_pct: float | None


class UsageOverviewSeriesPoint(BaseModel):
    date: date
    energy_kwh: float
    idle_energy_kwh: float


class UsageOverviewPeriod(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_date: date = Field(alias="from")
    to: date
    totals: UsageOverviewTotals
    series: list[UsageOverviewSeriesPoint]


class UsageOverviewChanges(BaseModel):
    energy_kwh_pct: float | None
    occupied_hours_pct: float | None
    utilization_pct: float | None
    idle_energy_kwh_pct: float | None
    idle_share_pct: float | None


class UsageOverviewRoom(BaseModel):
    room_id: int
    name: str
    occupied_hours: float
    scheduled_hours: float
    utilization_pct: float | None
    energy_kwh: float
    idle_energy_kwh: float


class UsageHourCell(BaseModel):
    average_occupied_minutes: float
    level: int


class UsageOverviewRead(BaseModel):
    period: UsageOverviewPeriodName
    current: UsageOverviewPeriod
    previous: UsageOverviewPeriod
    changes: UsageOverviewChanges
    rooms: list[UsageOverviewRoom]
    hour_heatmap: list[list[UsageHourCell]]
    has_dummy: bool
