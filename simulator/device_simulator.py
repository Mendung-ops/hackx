"""Simulator perangkat MQTT: meniru ESP32 panel/acunit, vision, dan tombol dosen.

Tanpa NTP dan tanpa `ts`, persis seperti di venue. Pakai (broker harus jalan):

    # 1) perangkat: menjawab perintah engine dan melaporkan state (biarkan jalan).
    #    Satu proses per jenis akun karena ACL: panel=lampu, acunit=AC.
    python -m simulator.device_simulator --user panel --password ... devices --kind panel --ids 1 3 5
    python -m simulator.device_simulator --user acunit --password ... devices --kind acunit --ids 2 4 6

    # 2) vision: kirim jumlah orang untuk satu ruang
    python -m simulator.device_simulator --user vision --password ... vision --room 1 --counts 0 0 0

    # 3) tombol dosen ditekan lama pada perangkat 1 (lampu) -> LOCAL, lock 2 menit
    python -m simulator.device_simulator --user panel --password ... press --device 1
"""
import argparse
import json
import time

import paho.mqtt.client as mqtt


def _client(args, client_id: str) -> mqtt.Client:
    c = mqtt.Client(mqtt.CallbackAPIVersion.VERSION2, client_id=client_id)
    if args.user:
        c.username_pw_set(args.user, args.password)
    c.connect(args.host, args.port, keepalive=30)
    return c


def _pub(c: mqtt.Client, topic: str, payload: dict, retain: bool = False) -> None:
    c.publish(topic, json.dumps(payload), qos=1, retain=retain).wait_for_publish(5)
    print(f"-> {topic} {json.dumps(payload)}")


def cmd_devices(args) -> None:
    p = args.prefix
    state: dict[int, str] = {i: "on" for i in args.ids}
    kind = {i: args.kind for i in args.ids}

    def report(c, i, last):
        _pub(c, f"{p}/{kind[i]}/{i}/state", {"state": state[i], "last_cmd_id": last}, retain=True)

    def on_connect(c, userdata, flags, rc, props):
        c.subscribe(f"{p}/cmd/+", qos=1)
        for i in args.ids:
            report(c, i, "BOOT")

    def on_message(c, userdata, msg):
        i = int(msg.topic.rsplit("/", 1)[1])
        if i not in state:
            return
        data = json.loads(msg.payload)
        state[i] = "on" if data["action"] == "turn_on" else "off"
        print(f"<- {msg.topic} {data['action']} (cmd_id={data['cmd_id']})")
        report(c, i, data["cmd_id"])

    c = _client(args, args.client_id or f"sim-{args.kind}")
    c.on_connect, c.on_message = on_connect, on_message
    print(f"simulator perangkat {args.ids} jalan; Ctrl+C untuk berhenti")
    c.loop_forever()


def cmd_vision(args) -> None:
    c = _client(args, args.client_id)
    c.loop_start()
    for n in args.counts:
        _pub(c, f"{args.prefix}/vision/{args.room}/occupancy", {"person_count": n})
        time.sleep(args.delay)
    c.loop_stop()


def cmd_press(args) -> None:
    c = _client(args, args.client_id)
    c.loop_start()
    _pub(
        c,
        f"{args.prefix}/panel/{args.device}/event",
        {"action": "turn_on", "last_cmd_id": "LOCAL"},
    )
    c.loop_stop()


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=1883)
    p.add_argument("--user", default="")
    p.add_argument("--password", default="")
    p.add_argument("--prefix", default="smartx")
    sub = p.add_subparsers(dest="cmd", required=True)

    d = sub.add_parser("devices", help="meniru ESP32 panel/acunit")
    d.add_argument("--kind", choices=["panel", "acunit"], required=True)
    d.add_argument("--ids", type=int, nargs="+", required=True)
    d.add_argument("--client-id", default=None, help="default: sim-<kind>")
    d.set_defaults(fn=cmd_devices)

    v = sub.add_parser("vision", help="kirim jumlah orang")
    v.add_argument("--room", type=int, required=True)
    v.add_argument("--counts", type=int, nargs="+", required=True)
    v.add_argument("--delay", type=float, default=1.0)
    v.add_argument("--client-id", default="sim-vision")
    v.set_defaults(fn=cmd_vision)

    b = sub.add_parser("press", help="tombol dosen ditekan lama (LOCAL)")
    b.add_argument("--device", type=int, required=True)
    b.add_argument("--client-id", default="sim-button")
    b.set_defaults(fn=cmd_press)

    args = p.parse_args()
    args.fn(args)
