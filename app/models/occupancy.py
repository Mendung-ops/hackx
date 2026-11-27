from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base, utcnow


class OccupancyRecord(Base):
    """Hasil deteksi jumlah orang di ruangan (mis. dari YOLOv8)."""

    __tablename__ = "occupancy_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    person_count: Mapped[int] = mapped_column(Integer, default=0)
    source: Mapped[str] = mapped_column(String(50), default="simulator")
    detected_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True
    )

    room: Mapped["Room"] = relationship(back_populates="occupancy_records")


from app.models.room import Room  # noqa: E402
