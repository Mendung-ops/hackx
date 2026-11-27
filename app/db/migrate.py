"""Migrasi skema ringan: menambah kolom baru ke tabel yang sudah ada.

Jalankan manual: python -m app.db.migrate

`Base.metadata.create_all` hanya membuat tabel baru, tidak menambah kolom ke
tabel lama. Skrip ini hanya MENAMBAH kolom yang belum ada (aman dijalankan
berulang, tidak menghapus atau mengubah data). Untuk SQLite file, DB dicadangkan
dulu ke <nama>.bak-<waktu> di folder yang sama.
"""
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, text

from app.db.session import engine, settings
from app.models import Camera, HourlyUsage

# tabel -> {kolom: definisi SQL}
ADDITIONS: dict[str, dict[str, str]] = {
    "devices": {
        "switch_code": "VARCHAR(20)",
        "lamp_count": "INTEGER",
        "watt_per_lamp": "FLOAT",
        "unit_count": "INTEGER",
        "watt_per_unit": "FLOAT",
        "module_note": "VARCHAR(200)",
        "active": "BOOLEAN NOT NULL DEFAULT 1",
    },
    "rooms": {
        "camera_id": "VARCHAR(100)",
        "camera_url": "VARCHAR(500)",
        "floor": "VARCHAR(20)",
    },
    "daily_usage": {
        "idle_on_minutes": "INTEGER NOT NULL DEFAULT 0",
        "idle_energy_kwh": "FLOAT NOT NULL DEFAULT 0",
    },
}


def _backup_sqlite() -> Path | None:
    url = engine.url
    if url.get_backend_name() != "sqlite" or not url.database or url.database == ":memory:":
        return None
    src = Path(url.database)
    if not src.is_file():
        return None
    dst = src.with_name(f"{src.name}.bak-{datetime.now():%Y%m%d-%H%M%S}")
    shutil.copy2(src, dst)
    return dst


def migrate() -> list[str]:
    """Tambah kolom yang belum ada. Mengembalikan daftar 'tabel.kolom' yang ditambah."""
    insp = inspect(engine)
    pending: list[tuple[str, str, str]] = []
    for table, cols in ADDITIONS.items():
        if not insp.has_table(table):
            continue  # tabel belum ada: create_all (seed/aplikasi) yang membuatnya lengkap
        existing = {c["name"] for c in insp.get_columns(table)}
        pending += [(table, name, ddl) for name, ddl in cols.items() if name not in existing]

    cameras_table_missing = insp.has_table("rooms") and not insp.has_table("cameras")
    hourly_table_missing = insp.has_table("rooms") and not insp.has_table("hourly_usage")
    if not pending and not cameras_table_missing and not hourly_table_missing:
        print("Skema sudah terbaru, tidak ada yang diubah.")
        return []

    backup = _backup_sqlite()
    if backup:
        print(f"Cadangan DB: {backup}")
    added: list[str] = []
    with engine.begin() as conn:
        for table, name, ddl in pending:
            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
            added.append(f"{table}.{name}")
        if hourly_table_missing:
            HourlyUsage.__table__.create(conn, checkfirst=True)
            added.append("hourly_usage")
        if cameras_table_missing:
            Camera.__table__.create(conn, checkfirst=True)
            conn.execute(text(
                "INSERT INTO cameras (room_id, name, camera_id, camera_url, active) "
                "SELECT id, 'CCTV utama', camera_id, camera_url, 1 FROM rooms "
                "WHERE camera_id IS NOT NULL AND camera_url IS NOT NULL "
                "AND TRIM(camera_id) <> '' AND TRIM(camera_url) <> ''"
            ))
            added.append("cameras")
    print("Kolom ditambah:", ", ".join(added))
    return added


if __name__ == "__main__":
    print(f"DB: {settings.database_url}")
    migrate()
