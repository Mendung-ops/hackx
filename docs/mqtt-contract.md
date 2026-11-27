# Kontrak MQTT (v1)

Kontrak antara backend (rule engine) dan perangkat lapangan: `vision` (kamera YOLOv8), `panel` (saklar lampu, ESP32), dan `acunit` (kontrol AC). Sumber kebenaran adalah kode di `app/services/mqtt_handler.py` dan `app/adapters/mqtt_bridge.py`; dokumen ini dicocokkan dengan kode tersebut.

## Broker

| Item | Nilai |
|---|---|
| Alamat | IP laptop backend di hotspot, port **1883** (tanpa TLS) |
| Akses anonim | Tidak diizinkan; tiap akun punya sandi (dibuat `deploy/mosquitto/setup.sh`) |
| Prefix topik | `smartx` (`MQTT_TOPIC_PREFIX`) |
| QoS | 1 untuk command, state, event, status, dan PIR |
| Retained | `state` dan `status` = ya; `cmd`, `event`, dan PIR = tidak |

Akun dan hak akses (`deploy/mosquitto/acl`):

| Akun | Boleh publish | Boleh subscribe |
|---|---|---|
| `vision` | `smartx/vision/#` | - |
| `panel` | `smartx/panel/#` | `smartx/cmd/#` |
| `acunit` | `smartx/acunit/#` | `smartx/cmd/#` |
| `engine` (backend) | `smartx/cmd/#` | `smartx/#` |
| `monitor` (P4) | - | `smartx/#` (hanya baca) |

Akun backend memakai `smartx/status/engine` (`online`/`offline`, retained). Perangkat panel memakai `smartx/panel/{device_id}/status` dengan Last Will `offline` dan publish `online` setelah terhubung; payload teks biasa dan retained. Monitor dapat membaca status retained untuk melihat kondisi terakhir.

## Aturan umum

- **`room_id` dan `device_id` berupa angka**, sama dengan ID di database.
- Payload berupa **JSON object**. Payload rusak atau ID yang tidak dikenal dicatat lalu diabaikan.
- Nilai memakai **huruf kecil**: `state` = `on`/`off`; `action` = `turn_on`/`turn_off`.
- **Tidak perlu mengirim `ts`.** Jika dikirim, diabaikan. Semua waktu adalah waktu terima di server (ESP32 tanpa NTP).

## Perangkat ke backend

| Topik | Payload | Keterangan |
|---|---|---|
| `smartx/vision/{room_id}/occupancy` | `{"person_count": 2}` | Bilangan bulat >= 0 (`count` juga diterima). Setiap pesan disimpan dan memicu aturan. |
| `smartx/panel/{device_id}/event` | `{"action":"turn_on","last_cmd_id":"LOCAL"}` | Tombol fisik ditekan. Hanya `last_cmd_id` = `LOCAL` yang diproses. `turn_off` mematikan; nilai lain dianggap `turn_on`. |
| `smartx/panel/{device_id}/state` | `{"state":"on","last_cmd_id":"<id>"}` | Laporan state terbaru; QoS 1, retained. `last_cmd_id` = `cmd_id` perintah yang baru dijalankan, atau `LOCAL` jika karena tombol fisik. |
| `smartx/acunit/{device_id}/state` | `{"state":"off","last_cmd_id":"<id>"}` | Sama seperti state panel; QoS 1, retained. |
| `smartx/panel/{device_id}/status` | `online` atau `offline` | Last Will dan status koneksi panel; QoS 1, retained. |
| `smartx/panel/{device_id}/pir` | `{"motion":true}` atau `{"motion":false}` | Telemetri PIR opsional; QoS 1, non-retained. Tidak menjadi input aturan okupansi saat ini. |

Laporan `LOCAL` lewat `event` dan `state` dalam jeda 2 detik dianggap satu penekanan, jadi firmware boleh mengirim keduanya.

## Backend ke perangkat

| Topik | Payload |
|---|---|
| `smartx/cmd/{device_id}` | `{"cmd_id":"a1b2c3d4e5f6","action":"turn_off","source":"engine"}` |

Command memakai QoS 1 dan **tidak retained**, supaya perintah lama tidak dijalankan ulang setelah reconnect.

Perangkat yang menjalankan perintah sebaiknya segera publish `.../state` dengan state baru dan `last_cmd_id` = `cmd_id` tersebut (ack).

## Perilaku backend

1. **Auto ON:** jika `person_count` sekurangnya `ON_MIN_PERSONS` (default 1) terus-menerus selama `ON_DELAY_SECONDS` (default 2 detik), engine mengirim `turn_on` ke perangkat lampu dan AC aktif yang belum menyala dengan `source: "engine"`. Nilai delay 0 menyalakan pada pembacaan pertama. Pembacaan di bawah ambang atau celah lebih panjang dari stale memulai hitungan dari awal. Perintah engine yang terkirim tidak diulang dalam jendela `VISION_STALE_SECONDS`; state yang sudah `on` juga mencegah duplikasi.
2. **Ruang kosong:** semua perangkat `on` dikirimi `turn_off` hanya setelah `person_count=0` berkelanjutan selama sekurangnya `EMPTY_DELAY_SECONDS` (default 20 detik). Satu pembacaan positif langsung mereset jeda. Timestamp pesan tidak dipakai; waktu dihitung saat pesan diterima server.
3. **Fail-safe kamera:** jika tidak ada occupancy lebih lama dari `VISION_STALE_SECONDS` (default 6 detik), ruang menjadi `UNKNOWN`; tidak ada ON/OFF dari occupancy dan timer kosong maupun terisi direset.
4. **Prioritas fisik 2 menit** (`LOCAL_LOCK_SECONDS`, default 120): setelah `LOCAL` + `turn_on`, rule engine tidak mengirim OFF ke perangkat itu. Setelah kunci habis, jeda kosong dimulai dari nol dan hanya data setelah akhir kunci yang dihitung. Kunci hanya memblokir OFF dari **rule**; OFF manual dari dashboard (`POST /commands`) tetap diproses.
5. **Retain:** `state` dan `status` retained agar klien baru menerima kondisi terakhir. `cmd`, `event`, dan PIR tidak retained. Pesan retained pada topik `state` hanya menyinkronkan state; pada topik `event` diabaikan seluruhnya. Karena itu firmware **jangan** memakai retain untuk tombol fisik.
6. **Ack:** pelacak ack (`app/services/ack_tracker.py`) sudah ditulis tetapi **belum dipasang** ke bridge; saat ini perintah berstatus `sent` begitu dipublish.
7. **Mode:** perintah hanya benar-benar dikirim jika `MQTT_ENABLED=true` dan `CONTROL_LIVE_MODE=true`; selain itu hanya dicatat (`dry_run`).

## ID pada data seed

| Ruang | `room_id` | Lampu (`panel`) | AC (`acunit`) |
|---|---|---|---|
| Kelas A101 | 1 | 1 | 2 |
| Kelas A102 | 2 | 3 | 4 |
| Kelas A103 | 3 | 5 | 6 |

**Perangkat tambahan lewat halaman admin.** Setiap sakelar lampu atau AC baru yang dibuat di `/admin` mendapat `device_id` baru (urut, melanjutkan nomor terakhir) dan topiknya mengikuti pola di atas: lampu memakai `smartx/panel/{device_id}/...`, AC memakai `smartx/acunit/{device_id}/state`, perintah selalu `smartx/cmd/{device_id}`. Satu ESP32 boleh melayani beberapa sakelar selama firmware subscribe ke `smartx/cmd/{id}` tiap sakelar dan mem-publish state/event dengan ID masing-masing. Backend tidak mencatat ESP32 mana yang memegang ID mana (hanya catatan bebas `module_note`). Daftar ID yang aktif ada di `GET /admin/devices` dan harus dikirim ke tim hardware setiap kali berubah. ID tidak pernah dipakai ulang; perangkat nonaktif tidak dikirimi perintah.

## Perintah AC simulasi

ESP32 AC saat ini hanya menampilkan status dari MQTT. Kontrak v1 menerima `turn_on` dan `turn_off` saja; `setback` dan `temp` belum didukung backend maupun skema command. Jika dibutuhkan setelah keputusan tim, tambahkan aksi eksplisit `set_temperature` dengan field `temp_c` pada kontrak dan API.

## Fail-safe okupansi

Backend memakai waktu terima server (UTC). Jika tidak ada pesan occupancy selama lebih dari `VISION_STALE_SECONDS` (default 6 detik), status ruang menjadi `UNKNOWN`; engine tidak mengirim ON/OFF dari occupancy dan mereset timer. Setelah data pulih, perangkat hanya dinyalakan setelah ambang `ON_MIN_PERSONS` berlanjut selama `ON_DELAY_SECONDS`; perangkat hanya dimatikan setelah nol berlanjut selama `EMPTY_DELAY_SECONDS` (default 20 detik). Kamera berhenti tidak pernah menyebabkan ON atau OFF. Belum ada integrasi jadwal; petugas mengikuti jadwal resmi secara manual ketika status `UNKNOWN`.

## Uji cepat

```bash
# Ulangi publish occupancy nol secara berkala selama ≥ EMPTY_DELAY_SECONDS.
# Jangan beri jeda > VISION_STALE_SECONDS di antara pesan.
# Contoh satu pesan (kirim berulang selama setidaknya 20 detik):
mosquitto_pub -h <IP> -u vision -P <sandi> -t smartx/vision/1/occupancy -m '{"person_count":0}'

# tombol fisik dosen pada panel 1
mosquitto_pub -h <IP> -u panel -P <sandi> -t smartx/panel/1/event -m '{"action":"turn_on","last_cmd_id":"LOCAL"}'

# pantau perintah dari backend
mosquitto_sub -h <IP> -u engine -P <sandi> -t 'smartx/cmd/#' -v
```

Simulator tanpa perangkat fisik: `python -m simulator.device_simulator --help`.
