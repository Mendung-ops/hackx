from datetime import date

from sqlalchemy import Date as SQLDate
from sqlalchemy import Float, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.session import Base


class DailyUsage(Base):
    """Riwayat harian untuk kalender; tidak dipakai layanan aturan kontrol."""

    __tablename__ = "daily_usage"
    __table_args__ = (
        UniqueConstraint("room_id", "date", name="uq_daily_usage_room_date"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    date: Mapped[date] = mapped_column(SQLDate, index=True)
    occupied_minutes: Mapped[int] = mapped_column(Integer, default=0)
    energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    idle_on_minutes: Mapped[int] = mapped_column(Integer, default=0)
    idle_energy_kwh: Mapped[float] = mapped_column(Float, default=0.0)
    source: Mapped[str] = mapped_column(String(20), default="dummy")
