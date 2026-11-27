from urllib.parse import unquote, urlsplit

from pydantic import BaseModel, ConfigDict, Field, field_validator


def clean_camera_url(v: str | None) -> str | None:
    """Kosong -> None; selain itu wajib http(s)://. Dipakai untuk membuat dan mengubah ruang."""
    if v is None:
        return None
    v = v.strip()
    if not v:
        return None
    try:
        parts = urlsplit(v)
        if parts.scheme.lower() not in {"http", "https"} or not parts.hostname:
            raise ValueError
        if parts.username is not None or parts.password is not None:
            raise ValueError("camera_url tidak boleh berisi kredensial")
        parts.port  # validasi port jika ada
    except ValueError as exc:
        if str(exc):
            raise
        raise ValueError("camera_url harus berupa URL http(s) yang valid") from exc
    return v


def camera_id_in_url(camera_id: str, camera_url: str) -> bool:
    path_ids = [unquote(part) for part in urlsplit(camera_url).path.split("/") if part]
    return camera_id in path_ids


def clean_label(v: str | None) -> str | None:
    """Gedung/lantai: spasi di ujung dibuang dan kosong -> None, supaya pengelompokan
    di dashboard tidak terpecah oleh 'Gedung A' vs 'Gedung A '."""
    if v is None:
        return None
    return v.strip() or None


class RoomCreate(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    building: str | None = Field(default=None, max_length=100)
    floor: str | None = Field(default=None, max_length=20)
    capacity: int | None = Field(default=None, ge=0)
    camera_id: str | None = Field(default=None, max_length=100)
    camera_url: str | None = Field(default=None, max_length=500)

    @field_validator("building", "floor")
    @classmethod
    def _label(cls, v):
        return clean_label(v)

    @field_validator("camera_url")
    @classmethod
    def _url(cls, v):
        return clean_camera_url(v)

    @field_validator("camera_id")
    @classmethod
    def _cam_id(cls, v):
        return (v.strip() or None) if v is not None else None


class RoomRead(RoomCreate):
    model_config = ConfigDict(from_attributes=True)

    id: int
