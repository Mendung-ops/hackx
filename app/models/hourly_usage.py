from datetime import date

from sqlalchemy import CheckConstraint, Date as SQLDate, Float, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class HourlyUsage(Base):
    """Profil penggunaan per jam untuk kalender dan ringkasan UI."""

    __tablename__ = "hourly_usage"
    __table_args__ = (
        UniqueConstraint("room_id", "date", "hour", name="uq_hourly_usage_room_date_hour"),
        CheckConstraint("hour >= 0 AND hour <= 23", name="ck_hourly_usage_hour"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    date: Mapped[date] = mapped_column(SQLDate, index=True)
    hour: Mapped[int] = mapped_column(Integer)
    occupied_minutes: Mapped[int] = mapped_column(Integer, default=0)
    energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
