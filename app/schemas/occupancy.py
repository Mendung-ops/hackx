from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.schemas.command import CommandRead


class OccupancyCreate(BaseModel):
    room_id: int
    person_count: int = Field(ge=0)
    source: str = "simulator"
    detected_at: datetime | None = None


class OccupancyRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    person_count: int
    source: str
    detected_at: datetime


class OccupancyResult(BaseModel):
    """Hasil POST /occupancy: data tersimpan + perintah otomatis yang terpicu."""

    record: OccupancyRead
    commands: list[CommandRead]
