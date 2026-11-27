from sqlalchemy import Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(100), unique=True, index=True)
    building: Mapped[str | None] = mapped_column(String(100), default=None)
    # Lantai sebagai teks bebas ("1", "2", "B1"): penomoran lantai tiap gedung ITB berbeda
    floor: Mapped[str | None] = mapped_column(String(20), default=None)
    capacity: Mapped[int | None] = mapped_column(Integer, default=None)
    # CCTV ruang ini (diatur lewat /admin): id/label kamera dan URL pemutar (MediaMTX)
    camera_id: Mapped[str | None] = mapped_column(String(100), default=None)
    camera_url: Mapped[str | None] = mapped_column(String(500), default=None)

    devices: Mapped[list["Device"]] = relationship(back_populates="room")
    occupancy_records: Mapped[list["OccupancyRecord"]] = relationship(
        back_populates="room"
    )
    cameras: Mapped[list["Camera"]] = relationship(back_populates="room")


from app.models.device import Device  # noqa: E402
from app.models.occupancy import OccupancyRecord  # noqa: E402
