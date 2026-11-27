from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.models.device import DeviceState, DeviceType


class DeviceCreate(BaseModel):
    room_id: int
    name: str = Field(min_length=1, max_length=100)
    type: DeviceType = DeviceType.LIGHT
    power_watt: float = Field(default=0.0, ge=0)


class DeviceRead(DeviceCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
    state: DeviceState
    last_changed_at: datetime | None = None
    switch_code: str | None = None
    lamp_count: int | None = None
    watt_per_lamp: float | None = None
    unit_count: int | None = None
    watt_per_unit: float | None = None
    module_note: str | None = None
    active: bool = True
