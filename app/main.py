from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text

from app.adapters.mqtt_bridge import get_bridge, start_bridge, stop_bridge
from app.api import admin, commands, dashboard, devices, occupancy, preview, schedules
from app.db.session import Base, SessionLocal, engine, settings
from app.services.schedule_service import seed_sample_schedules_if_empty
from app.services.usage_calendar_service import seed_dummy_daily_usage_if_empty
import app.models  # noqa: F401  (registrar seluruh tabel SQLAlchemy)


@asynccontextmanager
async def lifespan(_: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed_sample_schedules_if_empty(db)
        seed_dummy_daily_usage_if_empty(db)
    if settings.mqtt_enabled:
        start_bridge()
    yield
    stop_bridge()


app = FastAPI(
    title="HackX Classroom Energy Dashboard API", version="0.13.2", lifespan=lifespan
)

app.include_router(occupancy.router)
app.include_router(devices.router)
app.include_router(commands.router)
app.include_router(dashboard.router)
app.include_router(schedules.router)
app.include_router(preview.router)
app.include_router(admin.router)

# Frontend statis (frontend/index.html) disajikan dari origin yang sama
# dengan API, jadi tidak perlu CORS.
_FRONTEND_DIR = Path(__file__).resolve().parent.parent / "frontend"
if _FRONTEND_DIR.is_dir():
    app.mount("/ui", StaticFiles(directory=_FRONTEND_DIR, html=True), name="ui")

    @app.get("/", include_in_schema=False)
    def root():
        return RedirectResponse("/ui/")


@app.get("/health")
def health():
    """Cek API hidup dan koneksi DB berhasil."""
    with engine.connect() as conn:
        conn.execute(text("SELECT 1"))
    bridge = get_bridge()
    return {
        "status": "ok",
        "env": settings.app_env,
        "live_mode": settings.control_live_mode,
        "mqtt_enabled": settings.mqtt_enabled,
        "mqtt_connected": bool(bridge and bridge.connected),
    }
