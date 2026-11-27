"""Skema khusus halaman admin: pengaturan ruang, sakelar lampu, dan AC."""
from pydantic import BaseModel, ConfigDict, Field, SecretStr, field_validator, model_validator

from app.models.device import DeviceType
from app.schemas.device import DeviceRead
from app.schemas.room import RoomRead, camera_id_in_url, clean_camera_url, clean_label


class RoomUpdate(BaseModel):
    """Ubah sebagian data ruang; field yang tidak dikirim tidak berubah."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    building: str | None = Field(default=None, max_length=100)
    floor: str | None = Field(default=None, max_length=20)  # kosong = hapus
    capacity: int | None = Field(default=None, ge=0)
    camera_id: str | None = Field(default=None, max_length=100)
    camera_url: str | None = Field(default=None, max_length=500)  # kosong = hapus

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


class RoomAdminRead(RoomRead):
    device_count: int = 0  # hanya perangkat aktif


class CameraCreate(BaseModel):
    room_id: int
    name: str = Field(min_length=1, max_length=100)
    camera_id: str = Field(min_length=1, max_length=100)
    camera_url: str = Field(min_length=1, max_length=500)
    auth_username: str | None = Field(default=None, max_length=100)
    auth_password: SecretStr | None = None

    @field_validator("name", "camera_id")
    @classmethod
    def _nonblank(cls, v):
        value = v.strip()
        if not value:
            raise ValueError("field tidak boleh kosong")
        return value

    @field_validator("camera_url")
    @classmethod
    def _url(cls, v):
        value = clean_camera_url(v)
        if value is None:
            raise ValueError("camera_url wajib diisi")
        return value

    @field_validator("auth_username", mode="before")
    @classmethod
    def _username(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("auth_password", mode="before")
    @classmethod
    def _password(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def _id_in_url(self):
        if not camera_id_in_url(self.camera_id, self.camera_url):
            raise ValueError("ID CCTV harus menjadi salah satu segmen path URL sumber")
        if bool(self.auth_username) != bool(self.auth_password):
            raise ValueError("username dan password CCTV harus diisi bersamaan")
        return self


class CameraUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    camera_id: str | None = Field(default=None, max_length=100)
    camera_url: str | None = Field(default=None, max_length=500)
    active: bool | None = None
    auth_username: str | None = Field(default=None, max_length=100)
    auth_password: SecretStr | None = None
    clear_auth: bool = False

    @field_validator("name", "camera_id")
    @classmethod
    def _nonblank_optional(cls, v):
        if v is None:
            return None
        value = v.strip()
        if not value:
            raise ValueError("field tidak boleh kosong")
        return value

    @field_validator("camera_url")
    @classmethod
    def _url(cls, v):
        return clean_camera_url(v)

    @field_validator("auth_username", mode="before")
    @classmethod
    def _username(cls, value):
        return value.strip() or None if isinstance(value, str) else value

    @field_validator("auth_password", mode="before")
    @classmethod
    def _password(cls, value):
        return None if value == "" else value

    @model_validator(mode="after")
    def _auth_pair(self):
        if self.clear_auth and (self.auth_username is not None or self.auth_password is not None):
            raise ValueError("hapus login CCTV atau isi kredensial baru, jangan keduanya")
        if bool(self.auth_username) != bool(self.auth_password):
            raise ValueError("username dan password CCTV harus diisi bersamaan")
        return self

class CameraAdminRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    room_id: int
    name: str
    camera_id: str
    camera_url: str
    active: bool
    auth_configured: bool = False


class SwitchCreate(BaseModel):
    """Satu sakelar lampu atau satu unit AC = satu perangkat dengan satu ID MQTT.

    - light: wajib `lamp_count` dan `watt_per_lamp`; daya dihitung otomatis.
    - ac: isi `unit_count` dan `watt_per_unit` agar daya total dihitung otomatis.
      `power_watt` tetap diterima untuk kompatibilitas data lama.
    """

    room_id: int
    type: DeviceType
    name: str = Field(min_length=1, max_length=100)
    switch_code: str | None = Field(default=None, max_length=20)
    lamp_count: int | None = Field(default=None, ge=1, le=100)
    watt_per_lamp: float | None = Field(default=None, gt=0)
    unit_count: int | None = Field(default=None, ge=1, le=100)
    watt_per_unit: float | None = Field(default=None, gt=0)
    power_watt: float | None = Field(default=None, gt=0)
    module_note: str | None = Field(default=None, max_length=200)

    @model_validator(mode="after")
    def _check_by_type(self):
        if self.type == DeviceType.LIGHT:
            if self.lamp_count is None or self.watt_per_lamp is None:
                raise ValueError("sakelar lampu wajib mengisi lamp_count dan watt_per_lamp")
            if self.unit_count is not None or self.watt_per_unit is not None:
                raise ValueError("unit_count/watt_per_unit hanya untuk AC")
        else:
            if self.lamp_count is not None or self.watt_per_lamp is not None:
                raise ValueError("lamp_count/watt_per_lamp hanya untuk sakelar lampu")
            has_count, has_watt = self.unit_count is not None, self.watt_per_unit is not None
            if has_count != has_watt:
                raise ValueError("isi unit_count dan watt_per_unit bersamaan")
            if has_count and self.power_watt is not None:
                raise ValueError("power_watt dihitung dari unit_count x watt_per_unit")
            if not has_count and self.power_watt is None:
                raise ValueError("AC wajib mengisi unit_count + watt_per_unit atau power_watt")
        return self


class DeviceUpdate(BaseModel):
    """Ubah info switch dan daya; room_id/type tetap mengikuti ID firmware."""

    name: str | None = Field(default=None, min_length=1, max_length=100)
    switch_code: str | None = Field(default=None, max_length=20)
    lamp_count: int | None = Field(default=None, ge=1, le=100)
    watt_per_lamp: float | None = Field(default=None, gt=0)
    unit_count: int | None = Field(default=None, ge=1, le=100)
    watt_per_unit: float | None = Field(default=None, gt=0)
    power_watt: float | None = Field(default=None, gt=0)
    module_note: str | None = Field(default=None, max_length=200)
    active: bool | None = None


class DeviceTopics(BaseModel):
    """Topik MQTT yang harus dipakai firmware perangkat ini."""

    command: str  # backend publish, perangkat subscribe
    state: str  # perangkat publish
    event: str | None = None  # tombol fisik, hanya sakelar lampu (panel)


class DeviceAdminRead(DeviceRead):
    topics: DeviceTopics
