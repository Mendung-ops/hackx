from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.session import get_db
from app.models import Device
from app.schemas import DeviceRead

router = APIRouter(prefix="/devices", tags=["devices"])


@router.get("", response_model=list[DeviceRead])
def list_devices(room_id: int | None = None, db: Session = Depends(get_db)):
    stmt = select(Device).order_by(Device.id)
    if room_id is not None:
        stmt = stmt.where(Device.room_id == room_id)
    return db.scalars(stmt).all()


@router.get("/{device_id}", response_model=DeviceRead)
def get_device(device_id: int, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(status_code=404, detail=f"perangkat {device_id} tidak ditemukan")
    return device
