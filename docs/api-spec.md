# Spesifikasi API

Versi 0.13.2. Base URL lokal: `http://127.0.0.1:8000`. Dokumentasi interaktif otomatis: `/docs` (Swagger) dan `/redoc`.

Semua request dan respons berformat JSON. Waktu memakai ISO 8601, UTC tanpa zona.

## Ringkasan endpoint

| Method | Path | Fungsi |
|---|---|---|
| GET | `/health` | Cek API dan koneksi DB |
| POST | `/occupancy` | Kirim data okupansi, evaluasi aturan kontrol |
| GET | `/occupancy` | Riwayat okupansi |
| GET | `/occupancy/recent?limit_per_room=` | Riwayat terbaru per ruang untuk dashboard |
| GET | `/devices` | Daftar perangkat |
| GET | `/devices/{id}` | Detail satu perangkat |
| POST | `/commands` | Kirim perintah on/off manual |
| GET | `/commands` | Riwayat perintah (jejak alur kontrol) |
| GET | `/dashboard/overview` | Ringkasan semua ruang |
| GET | `/dashboard/energy` | Energi (kWh), emisi (kgCO2), estimasi penghematan |
| GET | `/dashboard/usage-calendar?room_id=&weeks=26&metric=occupancy` | Heatmap penggunaan harian untuk rekomendasi UI |
| GET | `/dashboard/usage-overview?period=7d` | Ringkasan energi, okupansi, utilisasi jadwal, dan energi saat ruang kosong |
| GET | `/schedules?room_id=` | Jadwal kelas mingguan (publik, hanya informasi) |
| GET | `/preview?room_id=` | Preview CCTV aktif per ruang (fallback `PREVIEW_URL`) |
| * | `/admin/*` | Atur ruang, switch lampu/AC, CCTV, dan jadwal (wajib `X-Admin-Token`, lihat bagian Admin) |

## Nilai enum

| Field | Nilai |
|---|---|
| `type` (perangkat) | `light`, `ac` |
| `state` (perangkat) | `on`, `off`, `unknown` |
| `action` (perintah) | `turn_on`, `turn_off` |
| `source` (perintah) | `manual`, `rule`, `engine`, `local` (otomatis engine dan tombol fisik hanya internal/MQTT; tidak bisa diisi lewat API) |
| `status` (perintah) | `pending`, `dry_run`, `sent`, `failed` |

## GET /health

```json
{ "status": "ok", "env": "dev", "live_mode": true,
  "mqtt_enabled": true, "mqtt_connected": true }
```

`live_mode` mengikuti `CONTROL_LIVE_MODE`. Jika `false`, perintah hanya dicatat (dry-run). `mqtt_enabled` mengikuti `MQTT_ENABLED`; `mqtt_connected` bernilai `true` hanya jika backend sedang tersambung ke broker. Gunakan ini untuk memastikan jalur MQTT hidup sebelum demo.

## POST /occupancy

Menyimpan satu pembacaan okupansi, lalu mengevaluasi aturan untuk ruang tersebut. Endpoint ini memerlukan header `X-Admin-Token: <ADMIN_TOKEN>`. Vision melalui MQTT tetap memakai kontrak MQTT.

Body:

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `room_id` | int | ya | Harus ada di tabel `rooms` |
| `person_count` | int ≥ 0 | ya | Jumlah orang terdeteksi |
| `source` | string | tidak | Default `simulator` |
| `detected_at` | datetime | tidak | Diterima untuk kompatibilitas; waktu tersimpan dan keputusan kontrol selalu memakai waktu terima server (UTC) |

Respons `201`: data tersimpan dan perintah otomatis yang terpicu. `turn_on` dikirim setelah okupansi sekurangnya `ON_MIN_PERSONS` berlangsung minimal `ON_DELAY_SECONDS`; `turn_off` dikirim setelah nol berlangsung minimal `EMPTY_DELAY_SECONDS`. Semua keputusan mensyaratkan data kamera masih segar; timestamp yang dikirim klien tidak mengubah waktu terima server. Contoh respons setelah jeda OFF terpenuhi:

```json
{
  "record": {
    "id": 3, "room_id": 1, "person_count": 0,
    "source": "simulator", "detected_at": "2026-10-19T07:01:32.424606"
  },
  "commands": [
    {
      "device_id": 1, "action": "turn_off", "source": "rule",
      "reason": "ruang kosong ≥20 detik (deteksi nol berkelanjutan)",
      "id": 1, "status": "sent",
      "created_at": "2026-10-19T07:01:32.431388",
      "executed_at": "2026-10-19T07:01:32.432067"
    }
  ]
}
```

Error: `404` jika `room_id` tidak ada; `422` jika body tidak valid (mis. `person_count` negatif).

Okupansi juga bisa masuk lewat MQTT (`smartx/vision/{room_id}/occupancy`), diproses dengan aturan yang sama dan disimpan dengan `source` = `mqtt-vision` dan `detected_at` = waktu terima server. Jika stream tidak mengirim pesan lebih lama dari `VISION_STALE_SECONDS` (default 6 detik), status menjadi `UNKNOWN` dan rule tidak mengirim OFF; jeda kosong dimulai ulang ketika data pulih. Lihat [mqtt-contract.md](mqtt-contract.md).

## GET /occupancy

Query: `room_id` (opsional), `limit` (1–500, default 50). Urutan terbaru dulu.

```json
[
  { "id": 3, "room_id": 1, "person_count": 0, "source": "simulator",
    "detected_at": "2026-10-19T07:01:32.424606" }
]
```


## GET /occupancy/recent

Query `limit_per_room` (1–500, default 50). Mengembalikan pembacaan terbaru per ruang dalam satu request; urutan dikelompokkan menurut ruang lalu waktu terbaru. Endpoint ini dipakai dashboard untuk menghindari satu request per ruang.

## GET /devices dan GET /devices/{id}

Query `/devices`: `room_id` (opsional). `/devices/{id}` mengembalikan `404` jika tidak ada.

```json
{
  "room_id": 1, "name": "Lampu Kelas A101", "type": "light",
  "power_watt": 120.0, "id": 1, "state": "on",
  "last_changed_at": "2026-10-19T07:01:32.350363"
}
```

## POST /commands

Perintah manual, mis. tombol di dashboard. Wajib header `X-Admin-Token: <ADMIN_TOKEN>`. Body:

| Field | Tipe | Wajib | Keterangan |
|---|---|---|---|
| `device_id` | int | ya | |
| `action` | enum | ya | `turn_on` / `turn_off` |
| `source` | enum | tidak | Default `manual` |
| `reason` | string ≤ 255 | tidak | Catatan alasan |

Respons `201`:

```json
{
  "device_id": 1, "action": "turn_on", "source": "manual",
  "reason": "tombol dashboard", "id": 3, "status": "sent",
  "created_at": "2026-10-19T07:01:32.446496",
  "executed_at": "2026-10-19T07:01:32.446972"
}
```

`status` bergantung pada mode: `sent` (live), `dry_run` (dry-run), atau `failed` (adapter gagal; HTTP tetap `201` karena perintah tercatat, cek `status` dan `reason`). Error: `404` jika perangkat tidak ada; `422` jika `source` = `local` atau `engine` (keduanya internal); `409` jika `source` = `rule` dengan `turn_off` ke perangkat yang sedang dikunci prioritas fisik.

Catatan prioritas fisik: setelah tombol dosen ditekan (`LOCAL` + `turn_on`), OFF dari **rule** ditolak selama `LOCAL_LOCK_SECONDS` (default 120 detik). Perintah `manual` dari dashboard tidak ikut terkunci.

## GET /commands

Query: `device_id` (opsional), `limit` (1–500, default 50). Terbaru dulu. Bentuk item sama dengan respons `POST /commands`. Gunakan ini untuk menelusuri siapa (`source`), kapan, dan mengapa (`reason`) sebuah perangkat berubah.

## GET /dashboard/overview

Ringkasan untuk tampilan dashboard. Contoh (dipotong ke satu ruang):

```json
{
  "live_mode": true,
  "total_devices_on": 5,
  "total_power_watt_now": 2160.0,
  "rooms": [
    {
      "room": { "name": "Kelas A101", "building": "Gedung A", "capacity": 40, "id": 1 },
      "devices": [
        { "room_id": 1, "name": "Lampu Kelas A101", "type": "light",
          "power_watt": 120.0, "id": 1, "state": "on",
          "last_changed_at": "2026-10-19T07:01:32.446972" }
      ],
      "latest_person_count": 0,
      "last_detected_at": "2026-10-19T07:01:32.424606",
      "devices_on": 1,
      "power_watt_now": 120.0
    }
  ]
}
```

`power_watt_now` adalah jumlah `power_watt` perangkat yang berstatus `on` saat ini. Ini daya sesaat, bukan energi kumulatif (kWh).

## GET /dashboard/energy

Energi, emisi karbon, dan estimasi penghematan per perangkat dan total.

Query:

| Field | Tipe | Keterangan |
|---|---|---|
| `start` | datetime | Default: `end` dikurangi 24 jam |
| `end` | datetime | Default dan batas atas: waktu server |
| `room_id` | int | Opsional, batasi ke satu ruang |

Contoh respons (dipotong ke satu perangkat):

```json
{
  "start": "2026-10-18T07:13:19", "end": "2026-10-19T07:13:19",
  "live_mode": true,
  "emission_factor_kg_per_kwh": 0.87,
  "emission_factor_source": "Jamali 0,87 tCO2/MWh (...)",
  "total_energy_kwh": 73.4399, "total_saved_kwh": 0.0001,
  "total_co2_kg": 63.8927, "total_saved_co2_kg": 0.0001,
  "devices": [
    { "device_id": 1, "device_name": "Lampu Kelas A101", "room_id": 1,
      "type": "light", "power_watt": 120.0, "on_hours": 24.0,
      "energy_kwh": 2.88, "saved_kwh": 0.0,
      "co2_kg": 2.5056, "saved_co2_kg": 0.0 }
  ]
}
```

Cara hitung: dari perintah berstatus `sent` di tabel `commands`, dengan daya perangkat dianggap konstan saat ON. `saved_kwh` adalah estimasi: lamanya perangkat mati setelah perintah `rule` turn_off dibanding andai tetap menyala. Perintah `dry_run` tidak mengubah perangkat sehingga tidak menghasilkan penghematan. Tanpa riwayat perintah, dipakai state perangkat saat ini untuk seluruh jendela.

Error: `422` jika `start` ≥ `end`.

## GET /schedules

Query `room_id` opsional. Tanpa filter, semua jadwal ruang dikembalikan. Jadwal memakai `day_of_week` 0=Senin sampai 6=Minggu dan jam dinding setempat `HH:MM`; data ini hanya untuk informasi dan rekomendasi UI.

```json
[{"id":1,"room_id":1,"day_of_week":0,"start_time":"08:00","end_time":"12:00","title":"Pemrograman Web","active":true}]
```

## GET /dashboard/usage-overview

Parameter `period` bernilai `7d`, `30d`, atau `6m` (default `7d`). Periode berjalan berakhir hari ini; periode pembanding tepat sepanjang periode yang sama sebelumnya. `6m` memakai 182 hari, dengan seri mingguan. Nilai periode tidak valid menghasilkan HTTP `422`.

Respons memuat `current` dan `previous`, masing-masing dengan `from`, `to`, `totals`, dan `series`. Persentase perubahan berada di `changes`; bila nilai pembanding nol atau tidak tersedia, nilainya `null`. `rooms` berisi peringkat ruang pada periode berjalan. `utilization_pct` adalah jam terisi dibagi jam terjadwal aktif; nilainya `null` jika tidak ada jadwal. `hour_heatmap` berukuran 7 × 24, Senin sampai Minggu dan jam 00–23; setiap sel berisi rata-rata menit terisi per ruang-hari dan level kuartil 0–4. `has_dummy` menandai adanya histori contoh.

Energi dan energi saat ruang kosong adalah estimasi dari daya terpasang dikali waktu perangkat menyala, bukan pembacaan meter. Energi saat kosong hanya dihitung saat pembacaan okupansi nyata menyatakan ruang kosong dan setidaknya satu perangkat menyala. Endpoint ini hanya untuk tampilan dan tidak dibaca rule engine.

Contoh bagian `current.totals`:

```json
{
  "energy_kwh": 34.5,
  "occupied_hours": 61.2,
  "scheduled_hours": 70.0,
  "utilization_pct": 87.43,
  "idle_energy_kwh": 5.2,
  "idle_share_pct": 15.07
}
```

## GET /dashboard/usage-calendar

Query `room_id` opsional (tanpa filter = gabungan semua ruang), `weeks` 1–52 (default 26), dan `metric` = `occupancy`, `energy`, atau `scheduled`. Endpoint mengembalikan satu entri per tanggal, termasuk nilai metrik terpilih, level heatmap 0–4, sumber data, jam terisi, energi, jam terjadwal, dan jumlah sesi.

```json
{
  "metric":"occupancy","unit":"jam","from":"2026-04-24","to":"2026-10-22",
  "days":[{"date":"2026-10-21","value":6.5,"level":3,"source":"measured",
    "occupied_hours":6.5,"energy_kwh":3.2,"scheduled_hours":8.5,"classes":2}]
}
```

Level 0 berarti nilai nol. Nilai nonnol dibagi ke kuartil rentang respons; bila semua nilainya nol semua level bernilai 0. Hari dengan pembacaan nyata memakai `source: "measured"` dan menggantikan riwayat contoh pada ruang/tanggal itu. Agregat semua ruang memakai `source: "mixed"` bila pada tanggal yang sama ada data contoh dan terukur. Data ini untuk kalender UI dan tidak menjadi input rule engine.

## GET /preview

Dengan `room_id`, API mengembalikan kamera aktif yang terhubung ke kelas tersebut. Halaman pemutar seperti MediaMTX di port `8889` memakai `format: "page"` dan ditampilkan dalam iframe; URL `.m3u8` memakai `format: "hls"`.

```json
{
  "enabled": true,
  "format": "page",
  "url": "http://10.124.223.85:8889/kelas-demo-01/",
  "camera_id": "kelas-demo-01",
  "cameras": [
    {"id": 1, "name": "CCTV A", "camera_id": "kelas-demo-01",
     "url": "http://10.124.223.85:8889/kelas-demo-01/", "format": "page"}
  ]
}
```

Field datar (`url`, `camera_id`, `format`) tetap disediakan untuk kompatibilitas; `cameras` berisi semua feed aktif saat kelas punya konfigurasi kamera Admin. Bila kelas belum punya kamera, API menggunakan URL legacy pada `rooms` atau `PREVIEW_URL` global. `enabled=false` dan `url=null` berarti tidak ada sumber preview.

Untuk login HTTP Basic, `POST /admin/cameras` dan `PATCH /admin/cameras/{id}` menerima `auth_username` dan `auth_password` secara berpasangan. Kredensial hanya disimpan di memori proses dev, tidak di SQLite atau respons API; daftar Admin hanya mengembalikan `auth_configured`. `PATCH` dengan `clear_auth: true` menghapus login. Kredensial hilang saat server restart. Jika login aktif, `/preview` menggunakan URL proxy same-origin; proxy mengirim autentikasi ke origin dan jalur kamera yang dikonfigurasi, serta menolak redirect ke origin atau jalur lain.


## Admin: ruang, sakelar lampu, AC, CCTV, dan jadwal

Endpoint yang mengubah data (`POST /occupancy`, `POST /commands`, dan semua endpoint `/admin/*`) wajib header `X-Admin-Token: <ADMIN_TOKEN dari .env>`. Tanpa `ADMIN_TOKEN` di `.env` jawabannya `503`; token salah atau tanpa header `401`. Endpoint GET dashboard tetap dapat dibaca tanpa token. Frontend dibuka dari origin yang sama.

| Method | Path | Fungsi |
|---|---|---|
| GET | `/admin/ping` | Cek token benar |
| GET | `/admin/rooms` | Daftar kelas + `device_count` dan konfigurasi legacy |
| POST | `/admin/rooms` | Buat kelas (`name` unik, `409` bila kembar) |
| PATCH | `/admin/rooms/{id}` | Ubah `name`, `building`, `capacity` |
| GET | `/admin/devices?room_id=&include_inactive=true` | Daftar switch/perangkat beserta `topics` MQTT |
| POST | `/admin/devices` | Tambah switch lampu atau AC; ID dibuat otomatis |
| PATCH | `/admin/devices/{id}` | Ubah nama, kode switch, jumlah/watt unit, catatan, status aktif |
| GET | `/admin/cameras?room_id=&include_inactive=true` | Daftar kamera kelas |
| POST | `/admin/cameras` | Tambah kamera dengan nama, ID CCTV, URL sumber |
| PATCH | `/admin/cameras/{id}` | Ubah kamera atau aktifkan/nonaktifkan dari preview |
| POST | `/admin/schedules` | Tambah jadwal mingguan untuk satu ruang |
| PATCH | `/admin/schedules/{id}` | Ubah hari, waktu, judul, atau status aktif |
| DELETE | `/admin/schedules/{id}` | Hapus jadwal |
| POST | `/admin/schedules/seed-sample` | Isi jadwal contoh, idempoten |
| POST | `/admin/usage-calendar/seed-sample` | Isi tanggal riwayat contoh yang belum ada |

Body tambah jadwal:

```json
{"room_id":1,"day_of_week":0,"start_time":"08:00","end_time":"12:00","title":"Pemrograman Web","active":true}
```

`title` maksimal 100 karakter. Jam wajib tepat `HH:MM`, jam selesai harus setelah jam mulai. Jadwal aktif yang tumpang tindih pada ruang dan hari yang sama ditolak dengan HTTP `409` dan pesan jadwal yang berbenturan. Jadwal nonaktif tidak menghalangi jadwal aktif lain.

**Satu sakelar atau satu AC = satu perangkat = satu ID MQTT.** Contoh sakelar A yang menyalakan 3 lampu 12 W:

```json
POST /admin/devices
{"room_id": 1, "type": "light", "name": "Sakelar A", "switch_code": "A",
 "lamp_count": 3, "watt_per_lamp": 12, "module_note": "ESP32 relay 4-ch panel belakang"}
```

Respons `201`: semua field `DeviceRead` plus `topics`:

```json
{"id": 7, "type": "light", "power_watt": 36, "lamp_count": 3, "watt_per_lamp": 12,
 "state": "unknown", "active": true,
 "topics": {"command": "smartx/cmd/7", "state": "smartx/panel/7/state", "event": "smartx/panel/7/event"}}
```

Aturan: lampu wajib `lamp_count` + `watt_per_lamp`; AC baru sebaiknya memakai `unit_count` + `watt_per_unit`. `power_watt` dihitung otomatis sebagai jumlah unit × watt per unit. `power_watt` tetap diterima untuk AC lama yang belum menyimpan rincian unit. Satu device adalah satu jalur kontrol switch, sehingga 3 dari 9 lampu dapat dikontrol sendiri bila terhubung ke switch terpisah. Estimasi energi: `power_watt × jam ON ÷ 1000 = kWh` (contoh 36 W selama 1 jam = 0,036 kWh). `room_id` dan `type` tidak bisa diubah setelah dibuat. Perangkat baru berstatus `unknown` sampai melapor state. Perangkat nonaktif tidak dikendalikan rule engine dan tidak tampil di `/dashboard/overview`.

Setiap kamera harus terhubung ke `room_id`, memiliki `camera_id` unik di kelas tersebut, dan URL `http://` atau `https://` tanpa username/password yang memuat `camera_id` sebagai salah satu segmen path. Contoh: `camera_id: "kelas-demo-01"` dan `camera_url: "http://10.124.223.85:8889/kelas-demo-01/"`. URL tanpa segmen path, ID yang tidak cocok, URL berkredensial, dan skema selain HTTP(S) ditolak dengan `422`; frontend admin menerjemahkan detail validasi ke pesan per field. Login HTTP Basic opsional dimasukkan terpisah di Admin dan hanya disimpan selama proses server dev berjalan; fitur ini bukan penyimpanan kredensial produksi. Nonaktifkan kamera untuk menghapusnya dari preview tanpa menghapus konfigurasi.

Field baru di `GET /devices` dan `/dashboard/overview`: `switch_code`, `lamp_count`, `watt_per_lamp`, `unit_count`, `watt_per_unit`, `module_note`, `active` (opsional untuk menjaga kompatibilitas klien lama).

## Format error

| Kode | Kapan | Bentuk |
|---|---|---|
| `404` | Perangkat atau ruang tidak ditemukan | `{"detail": "perangkat 999 tidak ditemukan"}` |
| `409` | Perintah `rule` turn_off ditolak karena prioritas fisik | `{"detail": "perangkat 1 terkunci prioritas fisik, OFF dari rule ditolak"}` |
| `409` | `POST /commands` ke perangkat nonaktif; nama kelas kembar; atau ID CCTV kembar dalam kelas yang sama | `{"detail": "ID CCTV 'kelas-demo-01' sudah dipakai di ruang ini"}` |
| `401` | Endpoint mutasi tanpa token atau dengan token salah | `{"detail": "token admin salah atau tidak ada"}` |
| `503` | `ADMIN_TOKEN` belum diatur | `{"detail": "ADMIN_TOKEN belum diatur di .env; endpoint ini dinonaktifkan"}` |
| `422` | Validasi body/query gagal | `{"detail": [{"type": "...", "loc": ["body", "person_count"], "msg": "..."}]}` |

## Catatan perubahan kontrak

Perubahan bentuk endpoint dicatat di [changelog.md](changelog.md). Antarmuka MQTT (bukan HTTP) didokumentasikan di [mqtt-contract.md](mqtt-contract.md).
