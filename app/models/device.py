import enum
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class DeviceType(str, enum.Enum):
    LIGHT = "light"
    AC = "ac"


class DeviceState(str, enum.Enum):
    ON = "on"
    OFF = "off"
    UNKNOWN = "unknown"


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    type: Mapped[str] = mapped_column(String(20), default=DeviceType.LIGHT.value)
    state: Mapped[str] = mapped_column(String(20), default=DeviceState.UNKNOWN.value)
    power_watt: Mapped[float] = mapped_column(Float, default=0.0)
    last_changed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)
    # Info sakelar (diatur lewat /admin). Untuk lampu: power_watt = lamp_count x watt_per_lamp.
    switch_code: Mapped[str | None] = mapped_column(String(20), default=None)
    lamp_count: Mapped[int | None] = mapped_column(Integer, default=None)
    watt_per_lamp: Mapped[float | None] = mapped_column(Float, default=None)
    # Untuk AC: daya total = unit_count x watt_per_unit.
    unit_count: Mapped[int | None] = mapped_column(Integer, default=None)
    watt_per_unit: Mapped[float | None] = mapped_column(Float, default=None)
    module_note: Mapped[str | None] = mapped_column(String(200), default=None)
    # Nonaktif = tidak dikontrol rule engine dan tidak tampil di dashboard (data tetap ada).
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    room: Mapped["Room"] = relationship(back_populates="devices")
    commands: Mapped[list["Command"]] = relationship(back_populates="device")


from app.models.command import Command  # noqa: E402
from app.models.room import Room  # noqa: E402
