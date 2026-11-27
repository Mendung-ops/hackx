"""Kredensial HTTP Basic CCTV sementara untuk mode pengembangan."""
from threading import RLock


_credentials: dict[int, tuple[str, str]] = {}
_lock = RLock()


def set_camera_credentials(camera_id: int, username: str, password: str) -> None:
    with _lock:
        _credentials[camera_id] = (username, password)


def clear_camera_credentials(camera_id: int) -> None:
    with _lock:
        _credentials.pop(camera_id, None)


def get_camera_credentials(camera_id: int) -> tuple[str, str] | None:
    with _lock:
        return _credentials.get(camera_id)


def camera_has_credentials(camera_id: int) -> bool:
    return get_camera_credentials(camera_id) is not None
