"""Simulator okupansi: kirim data ke API seolah-olah dari YOLOv8.

Pakai (server harus jalan, CONTROL_LIVE_MODE=true agar efeknya terlihat):
    python -m simulator.occupancy_simulator --scenario kelas-bubar
    python -m simulator.occupancy_simulator --scenario deteksi-goyah --delay 0
"""
import argparse
import os
import time

import httpx

# Tiap skenario: deretan jumlah orang per pembacaan, per nama ruang.
SCENARIOS: dict[str, dict[str, list[int]]] = {
    # kelas selesai: ramai lalu kosong -> perangkat harus mati di pembacaan ke-3 kosong
    "kelas-bubar": {"Kelas A101": [25, 24, 12, 0, 0, 0, 0]},
    # satu deteksi 0 salah di tengah kelas -> perangkat TIDAK boleh mati
    "deteksi-goyah": {"Kelas A101": [18, 0, 17, 0, 19, 18]},
    # tiga ruang: ramai, bubar, selalu kosong
    "semua-ruang": {
        "Kelas A101": [30, 28, 30, 29],
        "Kelas A102": [20, 10, 0, 0, 0],
        "Kelas A103": [0, 0, 0, 0],
    },
}


def run(base_url: str, scenario: str, delay: float, admin_token: str) -> None:
    rooms = {r["name"]: r["id"] for r in _rooms(base_url)}
    plan = SCENARIOS[scenario]
    steps = max(len(v) for v in plan.values())
    headers = {"X-Admin-Token": admin_token} if admin_token else {}
    with httpx.Client(base_url=base_url, timeout=10, headers=headers) as http:
        for i in range(steps):
            for name, counts in plan.items():
                if i >= len(counts):
                    continue
                r = http.post(
                    "/occupancy",
                    json={"room_id": rooms[name], "person_count": counts[i], "source": "simulator"},
                )
                r.raise_for_status()
                cmds = r.json()["commands"]
                note = f" -> {len(cmds)} perintah {cmds[0]['action']} ({cmds[0]['status']})" if cmds else ""
                print(f"[{i + 1}/{steps}] {name}: {counts[i]} orang{note}")
            time.sleep(delay)


def _rooms(base_url: str) -> list[dict]:
    """Ambil ruang lewat /dashboard/overview."""
    r = httpx.get(f"{base_url}/dashboard/overview", timeout=10)
    r.raise_for_status()
    return [item["room"] for item in r.json()["rooms"]]


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--scenario", choices=SCENARIOS, default="kelas-bubar")
    p.add_argument("--base-url", default="http://127.0.0.1:8000")
    p.add_argument("--delay", type=float, default=1.0, help="detik antar putaran")
    p.add_argument("--admin-token", default=os.getenv("ADMIN_TOKEN", ""), help="token admin; default dari ADMIN_TOKEN")
    args = p.parse_args()
    run(args.base_url, args.scenario, args.delay, args.admin_token)
