import enum
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base, utcnow


class CommandAction(str, enum.Enum):
    TURN_ON = "turn_on"
    TURN_OFF = "turn_off"


class CommandSource(str, enum.Enum):
    MANUAL = "manual"  # ditekan dari dashboard
    RULE = "rule"  # dipicu aturan ruang kosong
    ENGINE = "engine"  # otomatis oleh engine, misalnya okupansi terkonfirmasi
    LOCAL = "local"  # tombol fisik di ruang (last_cmd_id = LOCAL); prioritas tertinggi


class CommandStatus(str, enum.Enum):
    PENDING = "pending"
    DRY_RUN = "dry_run"  # dicatat saja, tidak dikirim ke perangkat
    SENT = "sent"
    FAILED = "failed"


class Command(Base):
    """Jejak setiap perintah ke perangkat, supaya alur bisa dilacak."""

    __tablename__ = "commands"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    device_id: Mapped[int] = mapped_column(ForeignKey("devices.id"), index=True)
    action: Mapped[str] = mapped_column(String(20))
    source: Mapped[str] = mapped_column(String(20), default=CommandSource.MANUAL.value)
    status: Mapped[str] = mapped_column(String(20), default=CommandStatus.PENDING.value)
    reason: Mapped[str | None] = mapped_column(String(255), default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, default=utcnow, index=True
    )
    executed_at: Mapped[datetime | None] = mapped_column(DateTime, default=None)

    device: Mapped["Device"] = relationship(back_populates="commands")


from app.models.device import Device  # noqa: E402
