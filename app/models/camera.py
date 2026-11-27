from sqlalchemy import Boolean, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


class Camera(Base):
    """Satu feed CCTV/vision yang dapat dipratinjau untuk sebuah ruang."""

    __tablename__ = "cameras"
    __table_args__ = (
        UniqueConstraint("room_id", "camera_id", name="uq_camera_room_camera_id"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    room_id: Mapped[int] = mapped_column(ForeignKey("rooms.id"), index=True)
    name: Mapped[str] = mapped_column(String(100))
    camera_id: Mapped[str] = mapped_column(String(100))
    camera_url: Mapped[str] = mapped_column(String(500))
    active: Mapped[bool] = mapped_column(Boolean, default=True, server_default="1")

    room: Mapped["Room"] = relationship(back_populates="cameras")
