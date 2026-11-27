from datetime import datetime, timezone

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "dev"
    database_url: str = "sqlite:///./hackx.db"
    control_live_mode: bool = False
    # MQTT (broker di laptop; ESP32/vision/panel/acunit terhubung ke sini)
    mqtt_enabled: bool = False
    mqtt_host: str = "127.0.0.1"
    mqtt_port: int = 1883
    mqtt_username: str = ""
    mqtt_password: str = ""
    mqtt_client_id: str = "engine"
    mqtt_topic_prefix: str = "smartx"
    # Batas tunggu ack perangkat (detik). 0 = nonaktif (perintah tetap `sent` saat
    # dipublish). Aktifkan setelah firmware terbukti melapor state setelah perintah.
    mqtt_ack_timeout_seconds: float = 0.0
    # Prioritas fisik: setelah tombol dosen (LOCAL), rule engine tidak kirim OFF
    local_lock_seconds: int = 120
    # Jeda nol beruntun sebelum rule boleh mematikan perangkat.
    empty_delay_seconds: float = Field(default=20.0, ge=0)
    # Data kamera lebih lama dari ambang ini berstatus UNKNOWN dan mereset jeda kosong.
    vision_stale_seconds: float = Field(default=6.0, ge=0)
    # Konfirmasi okupansi sebelum engine menyalakan perangkat.
    on_min_persons: int = Field(default=1, ge=1)
    on_delay_seconds: float = Field(default=2.0, ge=0)
    # URL pemutar MediaMTX (HLS) untuk live preview di dashboard; kosong = nonaktif
    preview_url: str = ""
    # Token halaman/endpoint admin (header X-Admin-Token). Kosong = /admin ditolak (503).
    admin_token: str = ""
    # Faktor emisi listrik (kgCO2 per kWh = tCO2 per MWh). Default: sistem Jamali.
    emission_factor_kg_per_kwh: float = 0.87
    emission_factor_source: str = (
        "Jamali 0,87 tCO2/MWh (tabel JCM, merujuk dokumen ESDM 2019); "
        "verifikasi dengan nilai ESDM terbaru sebelum disitasi"
    )


settings = Settings()

_connect_args = (
    {"check_same_thread": False} if settings.database_url.startswith("sqlite") else {}
)
engine = create_engine(
    settings.database_url, connect_args=_connect_args, pool_pre_ping=True
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


class Base(DeclarativeBase):
    """Base class semua model SQLAlchemy."""


def utcnow() -> datetime:
    """Waktu UTC saat ini (naive), pengganti datetime.utcnow() yang deprecated."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db():
    """Dependency FastAPI: satu session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
