"""Endpoint admin: atur ruang, sakelar lampu, dan AC.

Semua endpoint wajib header `X-Admin-Token` yang cocok dengan ADMIN_TOKEN di .env.
Perangkat tidak dihapus, hanya dinonaktifkan (`active=false`), supaya riwayat
perintah dan energinya tetap utuh.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Response
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.api.auth import require_admin
from app.db.session import get_db, settings
from app.models import Camera, Device, DeviceState, DeviceType, Room, Schedule
from app.schemas import DeviceRead, RoomCreate
from app.schemas.room import camera_id_in_url
from app.schemas.admin import (
    DeviceAdminRead,
    CameraAdminRead,
    CameraCreate,
    CameraUpdate,
    DeviceTopics,
    DeviceUpdate,
    RoomAdminRead,
    RoomUpdate,
    SwitchCreate,
)
from app.schemas.schedule import ScheduleCreate, ScheduleRead, ScheduleUpdate
from app.services.schedule_service import find_conflict, seed_sample_schedules
from app.services.usage_calendar_service import seed_dummy_daily_usage
from app.services.camera_auth import (
    camera_has_credentials,
    clear_camera_credentials,
    set_camera_credentials,
)

log = logging.getLogger("hackx.admin")


router = APIRouter(
    prefix="/admin", tags=["admin"], dependencies=[Depends(require_admin)]
)


def topics_for(device: Device) -> DeviceTopics:
    """Topik MQTT perangkat, sesuai docs/mqtt-contract.md."""
    p = settings.mqtt_topic_prefix
    is_light = device.type == DeviceType.LIGHT.value
    role = "panel" if is_light else "acunit"
    return DeviceTopics(
        command=f"{p}/cmd/{device.id}",
        state=f"{p}/{role}/{device.id}/state",
        event=f"{p}/panel/{device.id}/event" if is_light else None,
    )


def _read(device: Device) -> DeviceAdminRead:
    base = DeviceRead.model_validate(device).model_dump()
    return DeviceAdminRead(**base, topics=topics_for(device))


def _room_read(db: Session, room: Room) -> RoomAdminRead:
    count = db.scalar(
        select(func.count(Device.id)).where(
            Device.room_id == room.id, Device.active.is_(True)
        )
    )
    return RoomAdminRead(
        id=room.id,
        name=room.name,
        building=room.building,
        floor=room.floor,
        capacity=room.capacity,
        camera_id=room.camera_id,
        camera_url=room.camera_url,
        device_count=count or 0,
    )


@router.get("/ping")
def ping():
    """Cek token benar (dipakai halaman admin saat masuk)."""
    return {"ok": True}


@router.get("/rooms", response_model=list[RoomAdminRead])
def list_rooms(db: Session = Depends(get_db)):
    rooms = db.scalars(select(Room).order_by(Room.id)).all()
    return [_room_read(db, r) for r in rooms]


@router.post("/rooms", response_model=RoomAdminRead, status_code=201)
def create_room(data: RoomCreate, db: Session = Depends(get_db)):
    room = Room(**data.model_dump())
    db.add(room)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"ruang '{data.name}' sudah ada")
    log.info("admin: ruang %s dibuat (%s)", room.id, room.name)
    return _room_read(db, room)


@router.patch("/rooms/{room_id}", response_model=RoomAdminRead)
def update_room(room_id: int, data: RoomUpdate, db: Session = Depends(get_db)):
    room = db.get(Room, room_id)
    if room is None:
        raise HTTPException(404, f"ruang {room_id} tidak ditemukan")
    changes = data.model_dump(exclude_unset=True)
    if "name" in changes and changes["name"] is None:
        raise HTTPException(422, "name tidak boleh null")
    for key, value in changes.items():
        setattr(room, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, "nama ruang sudah dipakai ruang lain")
    log.info("admin: ruang %s diubah %s", room_id, sorted(changes))
    return _room_read(db, room)


@router.get("/cameras", response_model=list[CameraAdminRead])
def list_cameras(
    room_id: int | None = None,
    include_inactive: bool = True,
    db: Session = Depends(get_db),
):
    stmt = select(Camera).order_by(Camera.room_id, Camera.id)
    if room_id is not None:
        stmt = stmt.where(Camera.room_id == room_id)
    if not include_inactive:
        stmt = stmt.where(Camera.active.is_(True))
    return [
        CameraAdminRead.model_validate(camera).model_copy(
            update={"auth_configured": camera_has_credentials(camera.id)}
        )
        for camera in db.scalars(stmt).all()
    ]


def _camera_read(camera: Camera) -> CameraAdminRead:
    return CameraAdminRead.model_validate(camera).model_copy(
        update={"auth_configured": camera_has_credentials(camera.id)}
    )


@router.post("/cameras", response_model=CameraAdminRead, status_code=201)
def create_camera(data: CameraCreate, db: Session = Depends(get_db)):
    if db.get(Room, data.room_id) is None:
        raise HTTPException(404, f"ruang {data.room_id} tidak ditemukan")
    camera = Camera(
        **data.model_dump(exclude={"auth_username", "auth_password"}), active=True
    )
    db.add(camera)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"ID CCTV '{data.camera_id}' sudah dipakai di ruang ini")
    db.refresh(camera)
    if data.auth_username and data.auth_password:
        set_camera_credentials(
            camera.id, data.auth_username, data.auth_password.get_secret_value()
        )
    log.info("admin: CCTV %s ditambahkan di ruang %s", camera.camera_id, camera.room_id)
    return _camera_read(camera)


@router.patch("/cameras/{camera_pk}", response_model=CameraAdminRead)
def update_camera(camera_pk: int, data: CameraUpdate, db: Session = Depends(get_db)):
    camera = db.get(Camera, camera_pk)
    if camera is None:
        raise HTTPException(404, f"CCTV {camera_pk} tidak ditemukan")
    changes = data.model_dump(
        exclude_unset=True,
        exclude={"auth_username", "auth_password", "clear_auth"},
    )
    for key in ("name", "active"):
        if key in changes and changes[key] is None:
            raise HTTPException(422, f"{key} tidak boleh null")
    camera_id = changes.get("camera_id", camera.camera_id)
    camera_url = changes.get("camera_url", camera.camera_url)
    if not camera_id or not camera_url:
        raise HTTPException(422, "camera_id dan camera_url wajib tersedia")
    if ("camera_id" in changes or "camera_url" in changes) and not camera_id_in_url(camera_id, camera_url):
        raise HTTPException(422, "ID CCTV harus menjadi salah satu segmen path URL sumber")
    for key, value in changes.items():
        setattr(camera, key, value)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(409, f"ID CCTV '{camera_id}' sudah dipakai di ruang ini")
    if data.clear_auth or ("camera_url" in changes and not data.auth_username):
        clear_camera_credentials(camera.id)
    elif data.auth_username and data.auth_password:
        set_camera_credentials(
            camera.id, data.auth_username, data.auth_password.get_secret_value()
        )
    log.info("admin: CCTV %s diubah %s", camera_id, sorted(changes))
    return _camera_read(camera)


@router.get("/devices", response_model=list[DeviceAdminRead])
def list_devices(
    room_id: int | None = None,
    include_inactive: bool = True,
    db: Session = Depends(get_db),
):
    stmt = select(Device).order_by(Device.room_id, Device.id)
    if room_id is not None:
        stmt = stmt.where(Device.room_id == room_id)
    if not include_inactive:
        stmt = stmt.where(Device.active.is_(True))
    return [_read(d) for d in db.scalars(stmt).all()]


@router.post("/devices", response_model=DeviceAdminRead, status_code=201)
def create_device(data: SwitchCreate, db: Session = Depends(get_db)):
    """Tambah sakelar lampu atau AC. ID dibuat otomatis; berikan ID dan topiknya
    ke tim hardware, lalu catat di docs/mqtt-contract.md."""
    if db.get(Room, data.room_id) is None:
        raise HTTPException(404, f"ruang {data.room_id} tidak ditemukan")
    is_light = data.type == DeviceType.LIGHT
    device = Device(
        room_id=data.room_id,
        name=data.name,
        type=data.type.value,
        state=DeviceState.UNKNOWN.value,  # menunggu laporan state dari perangkat
        switch_code=data.switch_code,
        lamp_count=data.lamp_count if is_light else None,
        watt_per_lamp=data.watt_per_lamp if is_light else None,
        unit_count=data.unit_count if not is_light else None,
        watt_per_unit=data.watt_per_unit if not is_light else None,
        power_watt=(
            data.lamp_count * data.watt_per_lamp
            if is_light
            else data.unit_count * data.watt_per_unit
            if data.unit_count is not None and data.watt_per_unit is not None
            else data.power_watt
        ),
        module_note=data.module_note,
        active=True,
    )
    db.add(device)
    db.commit()
    log.info("admin: perangkat %s dibuat (%s, ruang %s)", device.id, device.type, device.room_id)
    return _read(device)


@router.patch("/devices/{device_id}", response_model=DeviceAdminRead)
def update_device(device_id: int, data: DeviceUpdate, db: Session = Depends(get_db)):
    device = db.get(Device, device_id)
    if device is None:
        raise HTTPException(404, f"perangkat {device_id} tidak ditemukan")
    changes = data.model_dump(exclude_unset=True)

    for key in ("name", "active"):
        if key in changes and changes[key] is None:
            raise HTTPException(422, f"{key} tidak boleh null")

    if device.type == DeviceType.LIGHT.value:
        if "power_watt" in changes:
            raise HTTPException(
                422, "daya sakelar lampu dihitung dari lamp_count x watt_per_lamp"
            )
        if "unit_count" in changes or "watt_per_unit" in changes:
            raise HTTPException(422, "unit_count/watt_per_unit hanya untuk AC")
        lamp_count = changes.get("lamp_count", device.lamp_count)
        watt_per_lamp = changes.get("watt_per_lamp", device.watt_per_lamp)
        if "lamp_count" in changes or "watt_per_lamp" in changes:
            if lamp_count is None or watt_per_lamp is None:
                raise HTTPException(
                    422,
                    "isi lamp_count dan watt_per_lamp sekaligus "
                    "(perangkat ini belum punya salah satunya)",
                )
            changes["power_watt"] = lamp_count * watt_per_lamp
    else:
        if "lamp_count" in changes or "watt_per_lamp" in changes:
            raise HTTPException(422, "lamp_count/watt_per_lamp hanya untuk sakelar lampu")
        if "unit_count" in changes or "watt_per_unit" in changes:
            if "power_watt" in changes:
                raise HTTPException(422, "daya AC dihitung dari unit_count x watt_per_unit")
            unit_count = changes.get("unit_count", device.unit_count)
            watt_per_unit = changes.get("watt_per_unit", device.watt_per_unit)
            if unit_count is None or watt_per_unit is None:
                raise HTTPException(422, "isi unit_count dan watt_per_unit bersamaan")
            changes["power_watt"] = unit_count * watt_per_unit
        elif "power_watt" in changes:
            if changes["power_watt"] is None:
                raise HTTPException(422, "power_watt tidak boleh null")
            if device.unit_count is not None or device.watt_per_unit is not None:
                raise HTTPException(422, "daya AC dihitung dari unit_count x watt_per_unit")

    for key, value in changes.items():
        setattr(device, key, value)
    db.commit()
    log.info("admin: perangkat %s diubah %s", device_id, sorted(changes))
    return _read(device)


def _validate_schedule_times(start_time: str, end_time: str) -> None:
    if end_time <= start_time:
        raise HTTPException(422, "jam selesai harus setelah jam mulai")


def _check_schedule_conflict(
    db: Session,
    *,
    room_id: int,
    day_of_week: int,
    start_time: str,
    end_time: str,
    active: bool,
    exclude_id: int | None = None,
) -> None:
    _validate_schedule_times(start_time, end_time)
    if not active:
        return
    conflict = find_conflict(
        db,
        room_id=room_id,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        exclude_id=exclude_id,
    )
    if conflict is not None:
        raise HTTPException(
            409,
            f"Jadwal bentrok dengan '{conflict.title}' "
            f"({conflict.start_time}–{conflict.end_time}) di ruang ini.",
        )


@router.post("/schedules", response_model=ScheduleRead, status_code=201)
def create_schedule(data: ScheduleCreate, db: Session = Depends(get_db)):
    if db.get(Room, data.room_id) is None:
        raise HTTPException(404, f"ruang {data.room_id} tidak ditemukan")
    _check_schedule_conflict(
        db,
        room_id=data.room_id,
        day_of_week=data.day_of_week,
        start_time=data.start_time,
        end_time=data.end_time,
        active=data.active,
    )
    schedule = Schedule(**data.model_dump())
    db.add(schedule)
    db.commit()
    db.refresh(schedule)
    log.info("admin: jadwal %s ditambahkan di ruang %s", schedule.id, schedule.room_id)
    return schedule


@router.patch("/schedules/{schedule_id}", response_model=ScheduleRead)
def update_schedule(
    schedule_id: int, data: ScheduleUpdate, db: Session = Depends(get_db)
):
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(404, f"jadwal {schedule_id} tidak ditemukan")
    changes = data.model_dump(exclude_unset=True)
    start_time = changes.get("start_time", schedule.start_time)
    end_time = changes.get("end_time", schedule.end_time)
    _check_schedule_conflict(
        db,
        room_id=schedule.room_id,
        day_of_week=changes.get("day_of_week", schedule.day_of_week),
        start_time=start_time,
        end_time=end_time,
        active=changes.get("active", schedule.active),
        exclude_id=schedule.id,
    )
    for key, value in changes.items():
        setattr(schedule, key, value)
    db.commit()
    db.refresh(schedule)
    log.info("admin: jadwal %s diubah %s", schedule_id, sorted(changes))
    return schedule


@router.delete("/schedules/{schedule_id}", status_code=204)
def delete_schedule(schedule_id: int, db: Session = Depends(get_db)):
    schedule = db.get(Schedule, schedule_id)
    if schedule is None:
        raise HTTPException(404, f"jadwal {schedule_id} tidak ditemukan")
    db.delete(schedule)
    db.commit()
    return Response(status_code=204)


@router.post("/schedules/seed-sample")
def seed_schedule_samples(db: Session = Depends(get_db)):
    result = seed_sample_schedules(db)
    log.info("admin: jadwal contoh dibuat=%s bentrok=%s", result["created"], result["skipped_conflicts"])
    return result


@router.post("/usage-calendar/seed-sample")
def seed_usage_samples(db: Session = Depends(get_db)):
    created = seed_dummy_daily_usage(db)
    log.info("admin: riwayat kalender contoh dibuat=%s", created)
    return {"created": created}
