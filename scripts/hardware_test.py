#!/usr/bin/env python3
"""Pengamat MQTT sementara untuk tes Control Success dan Response Time.

Jalankan dari root repo: python scripts/hardware_test.py
Skrip hanya subscribe MQTT; skrip tidak pernah publish command.
"""

from __future__ import annotations

import json
import queue
import sys
from datetime import datetime, timezone
from pathlib import Path
from threading import Event
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import paho.mqtt.client as mqtt

from app.db.session import settings


def ask_nonempty(prompt: str) -> str:
    while True:
        value = input(prompt).strip()
        if value:
            return value
        print("Nilai ini perlu diisi.")


def ask_id(prompt: str) -> int:
    while True:
        try:
            value = int(input(prompt).strip())
            if value > 0:
                return value
        except ValueError:
            pass
        print("Masukkan ID bilangan bulat lebih dari 0.")


def ask_yes_no(prompt: str) -> bool:
    while True:
        answer = input(f"{prompt} [y/n]: ").strip().lower()
        if answer in {"y", "ya"}:
            return True
        if answer in {"n", "tidak"}:
            return False
        print("Jawab y atau n.")


def stamp(value: datetime | None) -> str | None:
    return value.isoformat(timespec="milliseconds") if value else None


def main() -> int:
    print("UJI AKTUATOR — skrip pengamat saja, tidak mengirim command MQTT")
    print("Konfigurasi broker dibaca dari .env lokal dan tidak ditampilkan.\n")

    print("Checklist yang perlu P4 cek agar hasil tes valid:")
    print("  1. Pastikan room_id dan device_id cocok dengan ESP32 yang diuji.")
    print("  2. Mosquitto berjalan di Docker pada laptop P3; hotspot HP hanya menghubungkan perangkat.")
    print("     Pastikan ESP32 menunjuk ke IP hotspot laptop P3, port broker 1883, lalu berstatus online.")
    print("     ESP32 juga harus menerima command pada topic yang ditampilkan nanti.")
    print("  3. Pastikan state dikirim setelah output berubah, dengan last_cmd_id persis sama dengan cmd_id.")
    print("  4. Untuk Control Success, P4 harus bisa melihat output fisik dan menilai tiap command benar/salah.")
    print("     AC yang masih simulasi OLED tidak dihitung sebagai aksi fisik aktuator.")
    print("  5. Mulai semua skenario setelah monitor aktif; jangan kirim command sebelumnya.\n")

    print("Soal 1 — Control Success (data yang P3 minta dari P4)")
    room_id = ask_id("a) room_id: ")
    device_id = ask_id("b) device_id: ")
    while True:
        family = input("c) tipe perangkat [panel=lampu / acunit=AC]: ").strip().lower()
        if family in {"panel", "acunit"}:
            break
        print("Pilih panel atau acunit.")
    actuator = ask_nonempty("Nama aktuator/output yang diamati P4: ")
    p4_observer = ask_nonempty("Nama/inisial P4 yang mengonfirmasi aksi fisik: ")
    p4_ids_match = ask_yes_no("P4 sudah mencocokkan room_id dan device_id dengan ESP32 yang benar?")
    p4_can_observe = ask_yes_no("P4 siap melihat output fisik saat command diuji?")

    print("\nSoal 2 — Response Time (validasi balasan controller)")
    state_after_action = ask_yes_no("Firmware mengirim state setelah output berubah?")
    echo_cmd_id = ask_yes_no("State menggemakan cmd_id yang sama pada last_cmd_id?")
    p4_on_broker = ask_yes_no("P4 sudah memastikan ESP32 menuju IP hotspot laptop P3:1883 dan terhubung ke Mosquitto?")

    prefix = settings.mqtt_topic_prefix.rstrip("/")
    subscriptions = [
        (f"{prefix}/vision/{room_id}/occupancy", 1),
        (f"{prefix}/cmd/{device_id}", 1),
        (f"{prefix}/{family}/{device_id}/state", 1),
    ]
    print("Topic yang dipantau (cocokkan dengan konfigurasi firmware P4):")
    for topic, _qos in subscriptions:
        print(f"  {topic}")
    print("\nAmbang engine dari .env P3:")
    print(f"  ON: {settings.on_min_persons} orang selama {settings.on_delay_seconds:g} detik")
    print(f"  OFF: kosong {settings.empty_delay_seconds:g} detik; kamera basi {settings.vision_stale_seconds:g} detik")

    incoming: queue.Queue[dict[str, Any]] = queue.Queue()
    connected = Event()
    connect_error: list[str] = []
    client = mqtt.Client(
        mqtt.CallbackAPIVersion.VERSION2,
        client_id=f"p3-test-{datetime.now(timezone.utc):%H%M%S}",
    )
    if settings.mqtt_username:
        client.username_pw_set(settings.mqtt_username, settings.mqtt_password)

    def on_connect(client, userdata, flags, reason_code, properties) -> None:
        if reason_code.is_failure:
            connect_error.append(str(reason_code))
            connected.set()
            return
        result, _ = client.subscribe(subscriptions)
        if result != mqtt.MQTT_ERR_SUCCESS:
            connect_error.append(f"subscribe gagal (rc={result})")
        connected.set()

    def on_message(client, userdata, message) -> None:
        incoming.put({
            "at": datetime.now(timezone.utc),
            "topic": message.topic,
            "payload": message.payload.decode("utf-8", errors="replace"),
            "retained": bool(message.retain),
        })

    client.on_connect = on_connect
    client.on_message = on_message
    try:
        client.connect(settings.mqtt_host, settings.mqtt_port, keepalive=30)
    except OSError as exc:
        print(f"Tidak bisa menghubungi broker: {exc}")
        return 1
    client.loop_start()
    if not connected.wait(timeout=10) or connect_error:
        client.loop_stop()
        client.disconnect()
        detail = connect_error[0] if connect_error else "broker tidak merespons dalam 10 detik"
        print(f"Monitor gagal dimulai: {detail}")
        return 1

    events: list[dict[str, Any]] = []
    commands: list[dict[str, Any]] = []
    last_occupancy_at: datetime | None = None
    occupied: bool | None = None
    transition_at: datetime | None = None

    def process(event: dict[str, Any]) -> None:
        nonlocal last_occupancy_at, occupied, transition_at
        at: datetime = event["at"]
        topic: str = event["topic"]
        raw: str = event["payload"]
        retained = event["retained"]
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError:
            payload = raw
        events.append({
            "received_at_utc": stamp(at),
            "topic": topic,
            "payload": payload,
            "retained": retained,
        })
        time_label = stamp(at)

        if topic.endswith("/occupancy") and isinstance(payload, dict):
            count = payload.get("person_count", payload.get("count"))
            if not isinstance(count, int) or isinstance(count, bool) or count < 0:
                print(f"[{time_label}] occupancy tidak valid: {raw}")
                return
            stale = settings.vision_stale_seconds
            if last_occupancy_at and (at - last_occupancy_at).total_seconds() > stale:
                occupied = None
                transition_at = None
            now_occupied = count >= settings.on_min_persons
            if occupied is None or now_occupied != occupied:
                occupied = now_occupied
                transition_at = at
                event_name = "transisi okupansi"
            else:
                event_name = "sampel lanjutan"
            last_occupancy_at = at
            label = "terisi" if now_occupied else "kosong"
            print(f"[{time_label}] OCC {label}, {count} orang ({event_name})")
            return

        if topic == f"{prefix}/cmd/{device_id}" and isinstance(payload, dict):
            command_id = payload.get("cmd_id")
            if command_id and any(item["cmd_id"] == command_id for item in commands):
                print(f"[{time_label}] CMD duplikat diabaikan: {command_id}")
                return
            current_transition = transition_at
            if (
                last_occupancy_at is None
                or (at - last_occupancy_at).total_seconds() > settings.vision_stale_seconds
            ):
                current_transition = None
            command = {
                "cmd_id": command_id,
                "action": payload.get("action"),
                "command_at": at,
                "occupancy_at": current_transition,
                "response_at": None,
                "reported_state": None,
                "response_matches_action": None,
                "include_in_test": None,
                "physical_action_correct": None,
            }
            commands.append(command)
            print(f"[{time_label}] CMD {command['action']} cmd_id={command_id}")
            if current_transition:
                print(f"  transisi okupansi: {stamp(current_transition)} UTC")
            else:
                print("  tidak ada transisi okupansi segar sebelum command")
            return

        if topic.endswith("/state") and isinstance(payload, dict):
            command_id = payload.get("last_cmd_id")
            state = payload.get("state")
            if retained:
                print(f"[{time_label}] STATE retained diabaikan: {state}")
                return
            command = next(
                (item for item in reversed(commands)
                 if item["cmd_id"] == command_id and item["response_at"] is None),
                None,
            )
            if command is None:
                print(f"[{time_label}] STATE {state}, last_cmd_id={command_id} (tidak cocok)")
                return
            command["response_at"] = at
            command["reported_state"] = state
            expected = "on" if command["action"] == "turn_on" else "off"
            command["response_matches_action"] = state == expected
            command["occupancy_to_response_seconds"] = (
                (at - command["occupancy_at"]).total_seconds()
                if command["occupancy_at"] else None
            )
            command["command_to_response_seconds"] = (at - command["command_at"]).total_seconds()
            print(f"[{time_label}] STATE {state}, last_cmd_id={command_id} (cocok)")
            if command["occupancy_to_response_seconds"] is not None:
                print(f"  okupansi→state: {command['occupancy_to_response_seconds']:.3f} detik")

    print("\nMonitor aktif. Jalankan skenario setelah ini; tekan Ctrl+C untuk menghitung hasil.\n")
    try:
        while True:
            try:
                process(incoming.get(timeout=0.5))
            except queue.Empty:
                continue
    except KeyboardInterrupt:
        print("\nMengakhiri rekaman…")
    finally:
        client.loop_stop()
        client.disconnect()
    while not incoming.empty():
        process(incoming.get_nowait())

    successes = 0
    total_test_commands = 0
    for index, command in enumerate(commands, start=1):
        print(f"\nCommand {index}: {command['action']} / cmd_id={command['cmd_id']}")
        included = ask_yes_no("Apakah command ini termasuk skenario uji")
        command["include_in_test"] = included
        if not included:
            continue
        total_test_commands += 1
        if p4_can_observe:
            physical = ask_yes_no(f"Apakah P4 melihat {actuator} melakukan aksi yang diminta")
        else:
            physical = False
            print("Tidak dihitung sukses fisik karena tidak ada pengamat P4.")
        command["physical_action_correct"] = physical
        successes += int(physical)

    response_samples = [
        command["occupancy_to_response_seconds"]
        for command in commands
        if command["include_in_test"]
        and command.get("occupancy_to_response_seconds") is not None
    ]
    control_percent = successes / total_test_commands * 100 if total_test_commands else None
    average_response = sum(response_samples) / len(response_samples) if response_samples else None
    control_valid = p4_ids_match and p4_on_broker and p4_can_observe and total_test_commands > 0
    response_valid = (
        p4_ids_match and p4_on_broker and state_after_action and echo_cmd_id
        and bool(response_samples)
    )

    print("\nHASIL")
    print(
        f"Control Success: {successes}/{total_test_commands} = {control_percent:.1f}%"
        if control_percent is not None else "Control Success: N/A (belum ada command uji)"
    )
    print(
        f"Response Time okupansi→state echo: rata-rata {average_response:.3f} detik "
        f"dari {len(response_samples)} command"
        if average_response is not None
        else "Response Time: N/A (tidak ada pasangan transisi okupansi dan state echo)"
    )
    print("Catatan: P4 mengonfirmasi aksi fisik; skrip mengukur waktu saat pesan diterima P3.")
    print(
        "Validitas Control Success: SIAP dinilai"
        if control_valid else
        "Validitas Control Success: BELUM VALID — cek ID, koneksi broker, pengamat fisik, dan jumlah command."
    )
    print(
        "Validitas Response Time: SIAP dinilai"
        if response_valid else
        "Validitas Response Time: BELUM VALID — perlu transisi okupansi dan state segar yang menggemakan cmd_id."
    )

    generated_at = datetime.now(timezone.utc)
    result = {
        "generated_at_utc": stamp(generated_at),
        "room_id": room_id,
        "device_id": device_id,
        "device_family": family,
        "actuator_observed": actuator,
        "p4_observer": p4_observer,
        "p4_confirms_ids_match_device": p4_ids_match,
        "p4_can_observe_physical_output": p4_can_observe,
        "p4_confirms_state_after_actuation": state_after_action,
        "p4_confirms_cmd_id_echo": echo_cmd_id,
        "p4_confirms_broker_reachability": p4_on_broker,
        "engine_thresholds": {
            "on_min_persons": settings.on_min_persons,
            "on_delay_seconds": settings.on_delay_seconds,
            "empty_delay_seconds": settings.empty_delay_seconds,
            "vision_stale_seconds": settings.vision_stale_seconds,
        },
        "summary": {
            "control_success_correct": successes,
            "control_success_test_commands": total_test_commands,
            "control_success_percent": control_percent,
            "control_success_valid": control_valid,
            "response_time_samples": len(response_samples),
            "response_time_average_seconds": average_response,
            "response_time_valid": response_valid,
        },
        "commands": [
            {
                "cmd_id": command["cmd_id"],
                "action": command["action"],
                "command_at_utc": stamp(command["command_at"]),
                "occupancy_transition_at_utc": stamp(command["occupancy_at"]),
                "response_at_utc": stamp(command["response_at"]),
                "reported_state": command["reported_state"],
                "response_matches_action": command["response_matches_action"],
                "occupancy_to_response_seconds": command.get("occupancy_to_response_seconds"),
                "command_to_response_seconds": command.get("command_to_response_seconds"),
                "include_in_test": command["include_in_test"],
                "physical_action_correct": command["physical_action_correct"],
            }
            for command in commands
        ],
        "mqtt_events": events,
    }
    output_dir = ROOT / "test-results"
    output_dir.mkdir(exist_ok=True)
    output_path = output_dir / f"hardware-test-{generated_at:%Y%m%dT%H%M%SZ}.json"
    output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Data hasil tersimpan di: {output_path.relative_to(ROOT)}")

    if not state_after_action or not echo_cmd_id:
        print("PERHATIAN: response time belum tervalidasi; state harus dikirim setelah aksi dan menggemakan cmd_id.")
    if not p4_on_broker:
        print("PERHATIAN: P4 belum mengonfirmasi jangkauan broker; uji fisik perlu menunggu koneksi.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
