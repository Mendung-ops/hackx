import os

# Tes harus hasilnya sama di komputer siapa pun: environment variable menang atas `.env`,
# jadi nilai lokal (jeda kosong, token admin, MQTT, dll.) tidak memengaruhi tes.
# Nilai di bawah sama dengan default `Settings` di app/db/session.py. Harus ada sebelum `app` diimpor.
TEST_ENV_DEFAULTS = {
    "APP_ENV": "dev",
    "DATABASE_URL": "sqlite://",
    "CONTROL_LIVE_MODE": "false",
    "MQTT_ENABLED": "false",
    "MQTT_HOST": "127.0.0.1",
    "MQTT_PORT": "1883",
    "MQTT_USERNAME": "",
    "MQTT_PASSWORD": "",
    "MQTT_TOPIC_PREFIX": "smartx",
    "LOCAL_LOCK_SECONDS": "120",
    "EMPTY_DELAY_SECONDS": "20",
    "VISION_STALE_SECONDS": "6",
    "ON_MIN_PERSONS": "1",
    "ON_DELAY_SECONDS": "2",
    "PREVIEW_URL": "",
    "ADMIN_TOKEN": "",
}
os.environ.update(TEST_ENV_DEFAULTS)

import pytest
from datetime import datetime, timedelta
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

import app.models  # noqa: F401  (daftarkan semua tabel ke Base)
from app.adapters.device_adapter import SimulatedDeviceAdapter
from app.db.session import Base, get_db, settings, utcnow
from app.main import app
from app.models import Device, DeviceState, DeviceType, Room


class MutableClock:
    """Jam uji UTC naive yang dapat dimajukan tanpa menunggu."""

    def __init__(self, current=None):
        self.current = current or datetime(2026, 10, 22, 8, 0, 0)

    def __call__(self):
        return self.current

    def advance(self, seconds):
        self.current += timedelta(seconds=seconds)
        return self.current


@pytest.fixture()
def clock():
    return MutableClock()


@pytest.fixture()
def db():
    """DB SQLite in-memory baru untuk setiap tes."""
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()
    yield session
    session.close()
    engine.dispose()


@pytest.fixture()
def room(db):
    """Satu ruang dengan lampu (120 W) dan AC (900 W), keduanya menyala."""
    r = Room(name="Kelas T1", building="Gedung T", capacity=40)
    db.add(r)
    db.flush()
    for name, dtype, watt in [("Lampu", DeviceType.LIGHT, 120.0), ("AC", DeviceType.AC, 900.0)]:
        db.add(
            Device(
                room_id=r.id,
                name=f"{name} T1",
                type=dtype.value,
                state=DeviceState.ON.value,
                power_watt=watt,
                last_changed_at=utcnow(),
            )
        )
    db.commit()
    return r


@pytest.fixture()
def adapter():
    return SimulatedDeviceAdapter()


@pytest.fixture()
def client(db, monkeypatch):
    """TestClient dengan DB in-memory dan mode live menyala."""
    monkeypatch.setattr(settings, "control_live_mode", True)
    app.dependency_overrides[get_db] = lambda: db
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_headers(monkeypatch):
    """Header admin untuk tes endpoint tulis yang dilindungi token."""
    token = "token-uji"
    monkeypatch.setattr(settings, "admin_token", token)
    return {"X-Admin-Token": token}
