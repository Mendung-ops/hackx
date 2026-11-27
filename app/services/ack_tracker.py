"""Pelacak ack perintah ke perangkat (murni logika, tanpa ketergantungan ke broker).

Alur: bridge mem-publish perintah lalu `register()`. Perangkat menjawab dengan
pesan `.../state`; `ack()` menutup perintah yang menunggu. Perintah yang tidak
dijawab sampai `timeout` muncul di `expired()` dan ditandai `failed` oleh bridge.

Ack sah jika state yang dilaporkan sama dengan target perintah. `last_cmd_id`
yang sama dengan `cmd_id` dipakai lebih dulu untuk memilih perintah yang dijawab,
tetapi firmware yang tidak mengulang `cmd_id` tetap bisa meng-ack lewat state.
Timeout <= 0 menonaktifkan pelacakan (default; aktifkan setelah firmware teruji).
Daftar tunggu ada di memori: hilang saat server restart.
"""
import threading
import time
from dataclasses import dataclass
from typing import Callable


@dataclass(frozen=True)
class Pending:
    cmd_id: str
    device_id: int
    action: str  # "turn_on" | "turn_off"
    deadline: float


_TARGET = {"turn_on": "on", "turn_off": "off"}


class AckTracker:
    def __init__(self, timeout: float = 0.0, clock: Callable[[], float] = time.monotonic):
        self.timeout = timeout
        self._clock = clock
        self._pending: dict[str, Pending] = {}
        self._lock = threading.Lock()

    @property
    def enabled(self) -> bool:
        return self.timeout > 0

    def register(self, cmd_id: str, device_id: int, action: str) -> None:
        if not self.enabled:
            return
        with self._lock:
            self._pending[cmd_id] = Pending(
                cmd_id, device_id, action, self._clock() + self.timeout
            )

    def forget(self, cmd_id: str) -> None:
        with self._lock:
            self._pending.pop(cmd_id, None)

    def ack(self, device_id: int, last_cmd_id: str | None, state: str) -> bool:
        """True jika laporan state ini menjawab perintah yang sedang menunggu."""
        with self._lock:
            mine = [p for p in self._pending.values() if p.device_id == device_id]
            mine.sort(key=lambda p: p.cmd_id != last_cmd_id)  # cocok cmd_id lebih dulu
            for p in mine:
                if _TARGET.get(p.action) == state:
                    del self._pending[p.cmd_id]
                    return True
        return False

    def expired(self) -> list[Pending]:
        """Ambil (dan hapus) perintah yang lewat batas waktu."""
        now = self._clock()
        with self._lock:
            late = [p for p in self._pending.values() if p.deadline <= now]
            for p in late:
                del self._pending[p.cmd_id]
        return late

    def __len__(self) -> int:
        with self._lock:
            return len(self._pending)
