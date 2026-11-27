from datetime import datetime

from pydantic import BaseModel

from app.models.device import DeviceType


class DeviceEnergy(BaseModel):
    device_id: int
    device_name: str
    room_id: int
    type: DeviceType
    power_watt: float
    on_hours: float
    energy_kwh: float
    saved_kwh: float
    co2_kg: float
    saved_co2_kg: float


class EnergySummary(BaseModel):
    start: datetime
    end: datetime
    live_mode: bool
    emission_factor_kg_per_kwh: float
    emission_factor_source: str
    total_energy_kwh: float
    total_saved_kwh: float
    total_co2_kg: float
    total_saved_co2_kg: float
    devices: list[DeviceEnergy]
