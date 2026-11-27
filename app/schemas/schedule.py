from pydantic import BaseModel, ConfigDict, Field, field_validator


TIME_PATTERN = r"^(?:[01]\d|2[0-3]):[0-5]\d$"


class ScheduleCreate(BaseModel):
    room_id: int
    day_of_week: int = Field(ge=0, le=6)
    start_time: str = Field(pattern=TIME_PATTERN)
    end_time: str = Field(pattern=TIME_PATTERN)
    title: str = Field(min_length=1, max_length=100)
    active: bool = True

    @field_validator("title")
    @classmethod
    def _title_not_blank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("judul jadwal tidak boleh kosong")
        return value


class ScheduleUpdate(BaseModel):
    day_of_week: int | None = Field(default=None, ge=0, le=6)
    start_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    end_time: str | None = Field(default=None, pattern=TIME_PATTERN)
    title: str | None = Field(default=None, min_length=1, max_length=100)
    active: bool | None = None

    @field_validator("day_of_week", "start_time", "end_time", "title", "active")
    @classmethod
    def _no_null_updates(cls, value):
        if value is None:
            raise ValueError("field jadwal tidak boleh null")
        if isinstance(value, str) and not value.strip():
            raise ValueError("field jadwal tidak boleh kosong")
        return value.strip() if isinstance(value, str) else value


class ScheduleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    day_of_week: int
    start_time: str
    end_time: str
    title: str
    active: bool
