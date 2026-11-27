import pytest

from app.db.session import settings
from app.services import event_service

TOKEN = "token-uji"


@pytest.fixture()
def admin(client, monkeypatch):
    """Header admin yang valid (ADMIN_TOKEN diatur untuk tes ini)."""
    monkeypatch.setattr(settings, "admin_token", TOKEN)
    return {"X-Admin-Token": TOKEN}


def _light(room_id, **over):
    body = {
        "room_id": room_id,
        "type": "light",
        "name": "Sakelar A",
        "switch_code": "A",
        "lamp_count": 3,
        "watt_per_lamp": 12,
    }
    body.update(over)
    return body


def _post_occ(client, room_id, count, admin):
    return client.post(
        "/occupancy",
        json={"room_id": room_id, "person_count": count},
        headers=admin,
    )


# ---- akses -----------------------------------------------------------------

def test_admin_ditolak_jika_token_belum_diatur(client, monkeypatch):
    monkeypatch.setattr(settings, "admin_token", "")
    r = client.get("/admin/ping", headers={"X-Admin-Token": "apa-saja"})
    assert r.status_code == 503


def test_admin_token_salah_atau_tanpa_header_401(client, admin):
    assert client.get("/admin/ping").status_code == 401
    assert client.get("/admin/ping", headers={"X-Admin-Token": "salah"}).status_code == 401
    assert client.get("/admin/ping", headers=admin).status_code == 200


# ---- ruang -----------------------------------------------------------------

def test_buat_ruang_dan_duplikat_409(client, admin):
    r = client.post("/admin/rooms", json={"name": "Lab 1", "capacity": 30}, headers=admin)
    assert r.status_code == 201
    assert r.json()["device_count"] == 0
    dup = client.post("/admin/rooms", json={"name": "Lab 1"}, headers=admin)
    assert dup.status_code == 409


def test_ubah_ruang(client, admin, room):
    r = client.patch(f"/admin/rooms/{room.id}", json={"capacity": 55}, headers=admin)
    assert r.status_code == 200
    assert r.json()["capacity"] == 55
    assert r.json()["name"] == "Kelas T1"
    assert r.json()["device_count"] == 2
    assert client.patch("/admin/rooms/999", json={"capacity": 1}, headers=admin).status_code == 404


# ---- sakelar lampu dan AC --------------------------------------------------

def test_buat_sakelar_lampu_hitung_daya_dan_topik(client, admin, room):
    r = client.post("/admin/devices", json=_light(room.id), headers=admin)
    assert r.status_code == 201
    d = r.json()
    assert d["power_watt"] == 36  # 3 x 12
    assert d["lamp_count"] == 3 and d["watt_per_lamp"] == 12
    assert d["state"] == "unknown"
    assert d["active"] is True
    p = settings.mqtt_topic_prefix
    assert d["topics"] == {
        "command": f"{p}/cmd/{d['id']}",
        "state": f"{p}/panel/{d['id']}/state",
        "event": f"{p}/panel/{d['id']}/event",
    }


def test_buat_ac_topik_acunit_tanpa_event(client, admin, room):
    body = {"room_id": room.id, "type": "ac", "name": "AC 2", "power_watt": 750}
    r = client.post("/admin/devices", json=body, headers=admin)
    assert r.status_code == 201
    d = r.json()
    assert d["power_watt"] == 750
    assert d["lamp_count"] is None
    p = settings.mqtt_topic_prefix
    assert d["topics"]["state"] == f"{p}/acunit/{d['id']}/state"
    assert d["topics"]["event"] is None


def test_validasi_buat_perangkat(client, admin, room):
    no_lamp = _light(room.id)
    del no_lamp["lamp_count"]
    assert client.post("/admin/devices", json=no_lamp, headers=admin).status_code == 422
    ac_with_lamp = {"room_id": room.id, "type": "ac", "name": "AC", "power_watt": 900, "lamp_count": 2}
    assert client.post("/admin/devices", json=ac_with_lamp, headers=admin).status_code == 422
    ac_no_power = {"room_id": room.id, "type": "ac", "name": "AC"}
    assert client.post("/admin/devices", json=ac_no_power, headers=admin).status_code == 422
    assert client.post("/admin/devices", json=_light(999), headers=admin).status_code == 404


def test_daftar_perangkat_admin_memuat_semua_tipe(client, admin, room):
    r = client.get(f"/admin/devices?room_id={room.id}", headers=admin)
    assert r.status_code == 200
    assert {d["type"] for d in r.json()} == {"light", "ac"}
    assert all("topics" in d for d in r.json())


def test_ubah_lampu_hitung_ulang_daya(client, admin, room):
    dev = client.post("/admin/devices", json=_light(room.id), headers=admin).json()
    r = client.patch(f"/admin/devices/{dev['id']}", json={"lamp_count": 4}, headers=admin)
    assert r.status_code == 200
    assert r.json()["power_watt"] == 48  # 4 x 12
    r = client.patch(f"/admin/devices/{dev['id']}", json={"watt_per_lamp": 10}, headers=admin)
    assert r.json()["power_watt"] == 40


def test_ubah_perangkat_aturan_tipe(client, admin, room):
    dev = client.post("/admin/devices", json=_light(room.id), headers=admin).json()
    # daya lampu tidak boleh diisi langsung
    r = client.patch(f"/admin/devices/{dev['id']}", json={"power_watt": 99}, headers=admin)
    assert r.status_code == 422
    # AC (id 2 dari fixture) tidak punya lamp_count
    r = client.patch("/admin/devices/2", json={"lamp_count": 2}, headers=admin)
    assert r.status_code == 422
    r = client.patch("/admin/devices/2", json={"power_watt": 800}, headers=admin)
    assert r.status_code == 200 and r.json()["power_watt"] == 800
    assert client.patch("/admin/devices/999", json={"name": "x"}, headers=admin).status_code == 404


def test_lampu_lama_wajib_isi_dua_field_sekaligus(client, admin, room):
    # perangkat 1 dari fixture: lampu 120 W tanpa lamp_count/watt_per_lamp
    r = client.patch("/admin/devices/1", json={"lamp_count": 3}, headers=admin)
    assert r.status_code == 422
    r = client.patch(
        "/admin/devices/1", json={"lamp_count": 3, "watt_per_lamp": 40}, headers=admin
    )
    assert r.status_code == 200 and r.json()["power_watt"] == 120


# ---- nonaktif --------------------------------------------------------------

def test_perangkat_nonaktif_tidak_dikontrol_dan_tidak_tampil(client, admin, room, clock, monkeypatch):
    r = client.patch("/admin/devices/1", json={"active": False}, headers=admin)
    assert r.status_code == 200 and r.json()["active"] is False

    # dashboard hanya memuat perangkat aktif
    ov = client.get("/dashboard/overview").json()
    assert [d["id"] for d in ov["rooms"][0]["devices"]] == [2]
    assert ov["total_power_watt_now"] == 900

    # perintah manual ditolak
    cmd = client.post("/commands", json={"device_id": 1, "action": "turn_off"}, headers=admin)
    assert cmd.status_code == 409

    # Rule hanya mematikan AC setelah nol berkelanjutan 20 detik.
    monkeypatch.setattr(event_service, "server_clock", clock)
    cmds = []
    for _ in range(5):  # t=0, 5, 10, 15, 20
        cmds = _post_occ(client, room.id, 0, admin).json()["commands"]
        clock.advance(5)
    assert [c["device_id"] for c in cmds] == [2]

    # aktifkan lagi: perintah diterima
    client.patch("/admin/devices/1", json={"active": True}, headers=admin)
    assert client.post(
        "/commands", json={"device_id": 1, "action": "turn_off"}, headers=admin
    ).status_code == 201


# ---- kamera (CCTV) per ruang -----------------------------------------------

CAM_URL = "http://10.124.223.85:8889/kelas-demo-01/"


def test_kamera_ruang_diatur_dan_dihapus(client, admin, room):
    r = client.patch(
        f"/admin/rooms/{room.id}",
        json={"camera_id": " kelas-demo-01 ", "camera_url": CAM_URL},
        headers=admin,
    )
    assert r.status_code == 200
    assert r.json()["camera_id"] == "kelas-demo-01"
    assert r.json()["camera_url"] == CAM_URL
    # muncul juga di ringkasan dashboard
    ov = client.get("/dashboard/overview").json()
    assert ov["rooms"][0]["room"]["camera_url"] == CAM_URL
    # kosong = hapus
    r = client.patch(
        f"/admin/rooms/{room.id}", json={"camera_id": "", "camera_url": ""}, headers=admin
    )
    assert r.json()["camera_id"] is None and r.json()["camera_url"] is None


def test_url_kamera_harus_http(client, admin, room):
    r = client.patch(
        f"/admin/rooms/{room.id}", json={"camera_url": "rtsp://10.0.0.1/x"}, headers=admin
    )
    assert r.status_code == 422
    r = client.post(
        "/admin/rooms", json={"name": "Lab 9", "camera_url": "ftp://x"}, headers=admin
    )
    assert r.status_code == 422


def test_preview_per_ruang_dan_fallback_global(client, admin, room, monkeypatch):
    monkeypatch.setattr(settings, "preview_url", "")
    assert client.get(f"/preview?room_id={room.id}").json()["enabled"] is False

    client.patch(
        f"/admin/rooms/{room.id}",
        json={"camera_id": "kelas-demo-01", "camera_url": CAM_URL},
        headers=admin,
    )
    p = client.get(f"/preview?room_id={room.id}").json()
    assert p == {"enabled": True, "format": "page", "url": CAM_URL, "camera_id": "kelas-demo-01"}

    # tanpa room_id dan tanpa PREVIEW_URL: nonaktif; dengan PREVIEW_URL .m3u8: hls
    assert client.get("/preview").json()["enabled"] is False
    monkeypatch.setattr(settings, "preview_url", "http://x:8888/a/index.m3u8")
    g = client.get("/preview").json()
    assert g["enabled"] is True and g["format"] == "hls" and g["camera_id"] is None
    # ruang tanpa kamera memakai URL global
    client.patch(f"/admin/rooms/{room.id}", json={"camera_url": ""}, headers=admin)
    assert client.get(f"/preview?room_id={room.id}").json()["format"] == "hls"


@pytest.mark.parametrize(
    ("camera_id", "camera_url", "expected_message"),
    [
        (
            "kelas-demo-01",
            "http://demo:example@10.0.0.1:8889/kelas-demo-01/",
            "tidak boleh berisi kredensial",
        ),
        ("stream-lain", CAM_URL, "ID CCTV harus"),
        ("kelas-demo-01", "http://10.0.0.1:8889", "ID CCTV harus"),
        (
            "kelas-demo-01",
            "rtsp://10.0.0.1:554/kelas-demo-01",
            "URL http(s) yang valid",
        ),
    ],
    ids=["url-berkredensial", "id-tidak-ada-di-path", "url-tanpa-path", "url-rtsp"],
)
def test_buat_kamera_menjelaskan_penyebab_422(
    client, admin, room, camera_id, camera_url, expected_message
):
    response = client.post(
        "/admin/cameras",
        json={
            "room_id": room.id,
            "name": "CCTV uji",
            "camera_id": camera_id,
            "camera_url": camera_url,
        },
        headers=admin,
    )
    assert response.status_code == 422
    assert any(
        expected_message.lower() in error["msg"].lower()
        for error in response.json()["detail"]
    )


@pytest.mark.parametrize(
    ("camera_id", "camera_url", "expected_format"),
    [
        ("kelas-demo-01", "http://10.0.0.1:8889/kelas-demo-01/", "page"),
        (
            "kelas-demo-02",
            "http://10.0.0.2:8889/kelas-demo-02/stream.m3u8",
            "hls",
        ),
    ],
    ids=["mediamtx-page", "hls-playlist"],
)
def test_kamera_valid_tersimpan_muncul_dan_dipakai_preview(
    client, admin, room, camera_id, camera_url, expected_format
):
    response = client.post(
        "/admin/cameras",
        json={
            "room_id": room.id,
            "name": "CCTV uji",
            "camera_id": camera_id,
            "camera_url": camera_url,
        },
        headers=admin,
    )
    assert response.status_code == 201
    saved = response.json()
    assert saved["camera_url"] == camera_url

    listed = client.get(f"/admin/cameras?room_id={room.id}", headers=admin)
    assert listed.status_code == 200
    assert any(camera["id"] == saved["id"] for camera in listed.json())

    preview = client.get(f"/preview?room_id={room.id}").json()
    assert preview["enabled"] is True
    assert preview["format"] == expected_format
    assert preview["url"] == camera_url
    assert preview["cameras"][0]["camera_id"] == camera_id


# ---- gedung dan lantai -------------------------------------------------------

def test_gedung_dan_lantai_dirapikan_dan_muncul_di_overview(client, admin):
    r = client.post(
        "/admin/rooms",
        json={"name": "7602", "building": "  Labtek V ", "floor": " 6 "},
        headers=admin,
    )
    assert r.status_code == 201
    assert r.json()["building"] == "Labtek V" and r.json()["floor"] == "6"
    ov = client.get("/dashboard/overview").json()
    got = next(x for x in ov["rooms"] if x["room"]["name"] == "7602")
    assert got["room"]["building"] == "Labtek V" and got["room"]["floor"] == "6"


def test_ubah_dan_kosongkan_lantai(client, admin, room):
    r = client.patch(f"/admin/rooms/{room.id}", json={"floor": "2"}, headers=admin)
    assert r.status_code == 200 and r.json()["floor"] == "2"
    r = client.patch(f"/admin/rooms/{room.id}", json={"floor": "  "}, headers=admin)
    assert r.json()["floor"] is None
    assert r.json()["building"] == "Gedung T"  # field lain tidak ikut berubah


def test_lantai_terlalu_panjang_ditolak(client, admin):
    r = client.post(
        "/admin/rooms", json={"name": "X1", "floor": "1" * 21}, headers=admin
    )
    assert r.status_code == 422


def test_migrasi_menyertakan_kolom_floor():
    from app.db.migrate import ADDITIONS

    assert ADDITIONS["rooms"]["floor"] == "VARCHAR(20)"
