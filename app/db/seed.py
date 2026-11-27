"""Isi data contoh. Jalankan manual: python -m app.db.seed

Aman dijalankan berulang (idempotent). Membuat tabel yang belum ada,
jadi JANGAN dijalankan ke DB bersama sebelum skemanya dicek.
"""
from app.db.session import Base, SessionLocal, engine, utcnow
from app.models import Device, DeviceState, DeviceType, Room

ROOMS = ["Kelas A101", "Kelas A102", "Kelas A103"]
# (nama perangkat, tipe, daya watt)
DEVICES = [
    ("Lampu", DeviceType.LIGHT, 120.0),
    ("AC", DeviceType.AC, 900.0),
]


def seed() -> None:
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        for room_name in ROOMS:
            room = db.query(Room).filter_by(name=room_name).first()
            if room:
                continue
            room = Room(name=room_name, building="Gedung A", floor="1", capacity=40)
            db.add(room)
            db.flush()
            for name, dtype, watt in DEVICES:
                db.add(
                    Device(
                        room_id=room.id,
                        name=f"{name} {room_name}",
                        type=dtype.value,
                        state=DeviceState.ON.value,
                        power_watt=watt,
                        last_changed_at=utcnow(),
                    )
                )
        db.commit()
    print("Seed selesai.")


if __name__ == "__main__":
    seed()
