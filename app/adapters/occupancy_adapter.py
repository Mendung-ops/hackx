from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import Room
from app.schemas import OccupancyCreate


def to_occupancy(db: Session, payload: dict) -> OccupancyCreate:
    """Ubah payload deteksi mentah menjadi OccupancyCreate.

    Asumsi format payload (sesuaikan dengan keluaran YOLOv8 yang asli):
        {"room": "Kelas A101", "count": 2, "source": "yolov8",
         "timestamp": "2026-10-19T08:30:00"}   # source & timestamp opsional
    """
    room = db.scalar(select(Room).where(Room.name == payload["room"]))
    if room is None:
        raise LookupError(f"ruang '{payload['room']}' tidak ditemukan")
    ts = payload.get("timestamp")
    return OccupancyCreate(
        room_id=room.id,
        person_count=int(payload["count"]),
        source=payload.get("source", "yolov8"),
        detected_at=datetime.fromisoformat(ts) if ts else None,
    )
