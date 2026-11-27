from datetime import datetime

from pydantic import BaseModel

from app.schemas.device import DeviceRead
from app.schemas.room import RoomRead


class RoomOverview(BaseModel):
    room: RoomRead
    devices: list[DeviceRead]
    latest_person_count: int | None = None
    last_detected_at: datetime | None = None
    devices_on: int
    power_watt_now: float


class DashboardOverview(BaseModel):
    live_mode: bool
    total_devices_on: int
    total_power_watt_now: float
    rooms: list[RoomOverview]
