from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Schedule
from app.schemas.schedule import ScheduleRead

router = APIRouter(tags=["schedules"])


@router.get("/schedules", response_model=list[ScheduleRead])
def list_schedules(room_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Schedule).order_by(
        Schedule.room_id, Schedule.day_of_week, Schedule.start_time, Schedule.id
    )
    if room_id is not None:
        stmt = stmt.where(Schedule.room_id == room_id)
    return db.scalars(stmt).all()
