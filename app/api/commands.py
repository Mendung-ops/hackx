from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.db.session import get_db
from app.models import Command, CommandSource
from app.schemas import CommandCreate, CommandRead
from app.services.control_service import (
    DeviceInactive,
    DeviceNotFound,
    PhysicalLockActive,
    execute_command,
)

router = APIRouter(prefix="/commands", tags=["commands"])


@router.post("", response_model=CommandRead, status_code=201, dependencies=[Depends(require_admin)])
def post_command(data: CommandCreate, db: Session = Depends(get_db)):
    """Kirim perintah on/off ke perangkat (mis. tombol di dashboard)."""
    if data.source in (CommandSource.LOCAL, CommandSource.ENGINE):
        source_name = data.source.value
        origin = "tombol fisik lewat MQTT" if data.source == CommandSource.LOCAL else "rule engine"
        raise HTTPException(
            status_code=422,
            detail=f"source '{source_name}' hanya berasal dari {origin}",
        )
    try:
        return execute_command(
            db, data.device_id, data.action, data.source, data.reason
        )
    except DeviceNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except DeviceInactive as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    except PhysicalLockActive as exc:
        raise HTTPException(status_code=409, detail=str(exc))


@router.get("", response_model=list[CommandRead])
def list_commands(
    device_id: int | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Riwayat perintah, terbaru dulu: jejak alur kontrol."""
    stmt = select(Command).order_by(Command.id.desc())
    if device_id is not None:
        stmt = stmt.where(Command.device_id == device_id)
    return db.scalars(stmt.limit(limit)).all()
