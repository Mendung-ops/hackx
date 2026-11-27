from app.models import Room, Schedule


def _body(room_id, **changes):
    body = {
        "room_id": room_id,
        "day_of_week": 0,
        "start_time": "08:00",
        "end_time": "10:00",
        "title": "Pemrograman Web",
        "active": True,
    }
    body.update(changes)
    return body


def test_schedule_crud_and_filter_room(client, room, admin_headers, db):
    other = Room(name="Kelas T2")
    db.add(other)
    db.commit()
    first = client.post("/admin/schedules", json=_body(room.id), headers=admin_headers)
    assert first.status_code == 201
    second = client.post(
        "/admin/schedules", json=_body(other.id, title="Jaringan"), headers=admin_headers
    )
    assert second.status_code == 201

    listed = client.get(f"/schedules?room_id={room.id}")
    assert [item["id"] for item in listed.json()] == [first.json()["id"]]
    assert len(client.get("/schedules").json()) == 2

    updated = client.patch(
        f"/admin/schedules/{first.json()['id']}",
        json={"title": "Basis Data", "active": False},
        headers=admin_headers,
    )
    assert updated.status_code == 200
    assert updated.json()["title"] == "Basis Data" and not updated.json()["active"]
    deleted = client.delete(
        f"/admin/schedules/{second.json()['id']}", headers=admin_headers
    )
    assert deleted.status_code == 204
    assert len(client.get("/schedules").json()) == 1


def test_schedule_requires_admin_token(client, room, monkeypatch):
    from app.db.session import settings

    monkeypatch.setattr(settings, "admin_token", "token-uji")
    response = client.post("/admin/schedules", json=_body(room.id))
    assert response.status_code == 401


def test_schedule_validates_room_time_and_overlap(client, room, admin_headers):
    missing_room = client.post(
        "/admin/schedules", json=_body(999), headers=admin_headers
    )
    assert missing_room.status_code == 404

    invalid_time = client.post(
        "/admin/schedules", json=_body(room.id, start_time="8:00"), headers=admin_headers
    )
    assert invalid_time.status_code == 422
    invalid_order = client.post(
        "/admin/schedules", json=_body(room.id, start_time="10:00", end_time="10:00"),
        headers=admin_headers,
    )
    assert invalid_order.status_code == 422

    first = client.post("/admin/schedules", json=_body(room.id), headers=admin_headers)
    overlap = client.post(
        "/admin/schedules",
        json=_body(room.id, start_time="09:30", end_time="11:00", title="Basis Data"),
        headers=admin_headers,
    )
    assert overlap.status_code == 409
    assert "bentrok" in overlap.json()["detail"].lower()

    adjacent = client.post(
        "/admin/schedules",
        json=_body(room.id, start_time="10:00", end_time="11:00", title="Basis Data"),
        headers=admin_headers,
    )
    assert adjacent.status_code == 201
    changed = client.patch(
        f"/admin/schedules/{adjacent.json()['id']}",
        json={"start_time": "09:00"},
        headers=admin_headers,
    )
    assert changed.status_code == 409
    assert first.status_code == 201


def test_schedule_sample_seed_is_idempotent(client, room, admin_headers, db):
    first = client.post("/admin/schedules/seed-sample", headers=admin_headers)
    second = client.post("/admin/schedules/seed-sample", headers=admin_headers)
    assert first.status_code == second.status_code == 200
    assert first.json() == {"created": 5, "skipped_conflicts": 0}
    assert second.json() == {"created": 0, "skipped_conflicts": 0}
    assert db.query(Schedule).count() == 5
