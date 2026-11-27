from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.db.session import get_db
from app.models import OccupancyRecord
from app.schemas import (
    CommandRead,
    OccupancyCreate,
    OccupancyRead,
    OccupancyResult,
)
from app.services.event_service import RoomNotFound, handle_occupancy

router = APIRouter(prefix="/occupancy", tags=["occupancy"])


@router.post("", response_model=OccupancyResult, status_code=201, dependencies=[Depends(require_admin)])
def post_occupancy(data: OccupancyCreate, db: Session = Depends(get_db)):
    """Terima data okupansi (dari YOLOv8/simulator) lalu evaluasi aturan kontrol."""
    try:
        record, commands = handle_occupancy(db, data)
    except RoomNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return OccupancyResult(
        record=OccupancyRead.model_validate(record),
        commands=[CommandRead.model_validate(c) for c in commands],
    )


@router.get("/recent", response_model=list[OccupancyRead])
def recent_occupancy(
    limit_per_room: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    """Ambil pembacaan terbaru per ruang dalam satu permintaan dashboard."""
    ranked = (
        select(
            OccupancyRecord.id.label("record_id"),
            func.row_number()
            .over(
                partition_by=OccupancyRecord.room_id,
                order_by=(OccupancyRecord.detected_at.desc(), OccupancyRecord.id.desc()),
            )
            .label("row_number"),
        )
        .subquery()
    )
    stmt = (
        select(OccupancyRecord)
        .join(ranked, ranked.c.record_id == OccupancyRecord.id)
        .where(ranked.c.row_number <= limit_per_room)
        .order_by(
            OccupancyRecord.room_id,
            OccupancyRecord.detected_at.desc(),
            OccupancyRecord.id.desc(),
        )
    )
    return db.scalars(stmt).all()


@router.get("", response_model=list[OccupancyRead])
def list_occupancy(
    room_id: int | None = None,
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    stmt = select(OccupancyRecord).order_by(
        OccupancyRecord.detected_at.desc(), OccupancyRecord.id.desc()
    )
    if room_id is not None:
        stmt = stmt.where(OccupancyRecord.room_id == room_id)
    return db.scalars(stmt.limit(limit)).all()
