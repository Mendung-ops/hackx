from datetime import date
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


UsageMetric = Literal["occupancy", "energy", "scheduled"]


class UsageCalendarDay(BaseModel):
    date: date
    value: float
    level: int
    source: Literal["dummy", "measured", "mixed"] | None
    occupied_hours: float
    energy_kwh: float
    scheduled_hours: float
    classes: int


class UsageCalendarRead(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    metric: UsageMetric
    unit: str
    from_date: date = Field(alias="from")
    to: date
    days: list[UsageCalendarDay]
