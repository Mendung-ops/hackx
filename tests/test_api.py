from app.services import event_service

def _post_occ(client, room_id, count, admin_headers):
    return client.post(
        "/occupancy",
        json={"room_id": room_id, "person_count": count},
        headers=admin_headers,
    )


def test_health(client):
    r = client.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"


def test_occupancy_ruang_tidak_ada_404(client, admin_headers):
    assert _post_occ(client, 999, 1, admin_headers).status_code == 404


def test_occupancy_negatif_422(client, room, admin_headers):
    assert _post_occ(client, room.id, -1, admin_headers).status_code == 422


def test_alur_penuh_ruang_kosong_mematikan_perangkat(client, room, admin_headers, clock, monkeypatch):
    monkeypatch.setattr(event_service, "server_clock", clock)
    for _ in range(4):
        assert _post_occ(client, room.id, 0, admin_headers).json()["commands"] == []
        clock.advance(5)
    r = _post_occ(client, room.id, 0, admin_headers)
    assert r.status_code == 201
    cmds = r.json()["commands"]
    assert len(cmds) == 2
    assert {c["action"] for c in cmds} == {"turn_off"}
    assert {c["source"] for c in cmds} == {"rule"}

    ov = client.get("/dashboard/overview").json()
    assert ov["total_devices_on"] == 0
    assert ov["total_power_watt_now"] == 0
    assert ov["rooms"][0]["latest_person_count"] == 0


def test_perintah_manual_dan_riwayat(client, room, admin_headers):
    dev_id = client.get("/devices").json()[0]["id"]
    r = client.post(
        "/commands",
        json={"device_id": dev_id, "action": "turn_off", "reason": "tombol dashboard"},
        headers=admin_headers,
    )
    assert r.status_code == 201
    assert r.json()["status"] == "sent"
    assert client.get(f"/devices/{dev_id}").json()["state"] == "off"

    hist = client.get("/commands", params={"device_id": dev_id}).json()
    assert len(hist) == 1 and hist[0]["reason"] == "tombol dashboard"


def test_perintah_perangkat_tidak_ada_404(client, admin_headers):
    r = client.post(
        "/commands", json={"device_id": 999, "action": "turn_on"}, headers=admin_headers
    )
    assert r.status_code == 404


def test_energi_bentuk_respons(client, room):
    r = client.get("/dashboard/energy")
    assert r.status_code == 200
    body = r.json()
    assert len(body["devices"]) == 2
    assert body["emission_factor_kg_per_kwh"] > 0
    assert body["total_energy_kwh"] >= 0
    assert body["total_saved_kwh"] >= 0


def test_energi_rentang_terbalik_422(client, room):
    r = client.get(
        "/dashboard/energy",
        params={"start": "2026-10-19T10:00:00", "end": "2026-10-19T09:00:00"},
    )
    assert r.status_code == 422


def test_frontend_disajikan(client):
    r = client.get("/ui/")
    assert r.status_code == 200
    assert "Dashboard Energi Kelas" in r.text
    assert client.get("/", follow_redirects=False).headers["location"] == "/ui/"
