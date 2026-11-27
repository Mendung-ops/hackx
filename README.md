# HackX: Backend Dashboard Energi Ruang Kelas

Dashboard energi ruang kelas. Sistem menerima jumlah orang di tiap ruangan (dari kamera YOLOv8 atau simulator), mematikan lampu/AC lewat aturan saat ruang kosong, mencatat setiap perintah kontrol, dan menampilkan jadwal kelas serta pola penggunaan harian. Halaman **Ringkasan penggunaan** membandingkan jam terisi, utilisasi jadwal, dan estimasi energi saat ruang kosong. Jadwal dan histori penggunaan hanya informasi UI; tidak memengaruhi aturan perangkat.

Referensi: *An Intelligent System for Light and Air Conditioner Control Using YOLOv8* (JINITA 2024). Pembeda: perhitungan emisi karbon dari hasil penghematan (direncanakan).

Backend (FastAPI) sekaligus menyajikan frontend statis, jadi **hanya ada satu server** yang perlu dijalankan.

## Prasyarat

| Kebutuhan | Keterangan |
|---|---|
| Git | untuk clone |
| Python 3.13 | versi yang dipakai dan diuji proyek ini (Linux). Versi lain belum diverifikasi |
| Node.js (opsional) | hanya untuk tes frontend (`node --test`); diuji dengan Node 24 |
| Docker (opsional) | hanya untuk broker MQTT Mosquitto, lihat [Menjalankan dengan perangkat](#menjalankan-dengan-perangkat-mqtt) |

Untuk demo tanpa perangkat, cukup Git dan Python. Broker MQTT, perangkat ESP32, kamera, dan aliran CCTV **tidak diperlukan**; lihat [docs/HOW_TO_RUN.md](docs/HOW_TO_RUN.md) untuk bagian yang bergantung pada layanan eksternal.

## Mulai cepat (dari clone sampai dashboard tampil)

```bash
# 1. Clone
git clone https://github.com/Mendung-ops/hackx.git
cd hackx

# 2. Virtual environment dan dependensi
python3 -m venv .venv
source .venv/bin/activate            # Windows PowerShell: .venv\Scripts\Activate.ps1 (belum diverifikasi)
pip install -r requirements.txt

# 3. Konfigurasi
cp .env.example .env
```

Edit `.env`, minimal dua nilai ini agar demo berfungsi penuh:

```bash
# token untuk halaman Admin dan endpoint POST; buat string acak:
python -c "import secrets; print(secrets.token_urlsafe(32))"
# lalu isi: ADMIN_TOKEN=<hasil di atas>
# dan ubah: CONTROL_LIVE_MODE=true     (supaya state perangkat benar-benar berubah di demo)
```

```bash
# 4. Buat database demo (3 ruang, 6 perangkat) di hackx.db
python -m app.db.seed

# 5. Jalankan server (backend + frontend)
uvicorn app.main:app --reload
```

Jalankan perintah dari **folder root repository**: `.env` dan `hackx.db` dibaca relatif terhadap folder tempat perintah dijalankan.

Saat server mulai, jadwal contoh dan histori penggunaan dummy (26 minggu, per hari dan per jam) terisi otomatis jika tabelnya masih kosong, jadi dashboard langsung berisi data.

| URL | Isi |
|---|---|
| http://127.0.0.1:8000/ | dialihkan ke dashboard |
| http://127.0.0.1:8000/ui/ | dashboard (frontend): daftar ruang, `#/penggunaan` ringkasan penggunaan, `#/ruang/1` detail ruang |
| http://127.0.0.1:8000/ui/#/admin | Admin (masukkan `ADMIN_TOKEN`) |
| http://127.0.0.1:8000/docs | dokumentasi interaktif semua endpoint |
| http://127.0.0.1:8000/health | cek cepat: API, DB, status MQTT |

`hackx.db` **tidak ikut repository** (lihat `.gitignore`); database dibuat ulang oleh perintah seed di atas. Panduan lengkap dan pemecahan masalah ada di [docs/HOW_TO_RUN.md](docs/HOW_TO_RUN.md).

Jika Anda sudah punya `hackx.db` dari versi lama, jalankan `python -m app.db.migrate` sebelum server (cadangan otomatis dibuat sebagai `hackx.db.bak-<waktu>`). Semua energi di dashboard adalah estimasi daya terpasang dikali lama menyala, bukan hasil ukur meter.

## Menjalankan tes dan simulator

```bash
python -m pytest                 # 107 tes, DB in-memory, tidak menyentuh hackx.db (jangan pakai -q)
cd frontend && node --test       # 4 tes frontend (opsional, butuh Node.js)

# Simulator okupansi (server harus jalan dengan CONTROL_LIVE_MODE=true dan ADMIN_TOKEN terisi;
# simulator membaca token dari variabel lingkungan, bukan dari .env):
export ADMIN_TOKEN=<token yang sama dengan .env>
python -m simulator.occupancy_simulator --scenario kelas-bubar
# skenario lain: deteksi-goyah, semua-ruang
```

Dengan default `EMPTY_DELAY_SECONDS=20`, skenario simulator berdurasi beberapa detik belum membuat perangkat mati. Turunkan `EMPTY_DELAY_SECONDS` (mis. `2`) di `.env` untuk mencoba simulator, atau ikuti [docs/demo-script.md](docs/demo-script.md).

## Mulai dari sini (untuk anggota tim baru)

1. Baca bagian paling atas `docs/changelog.md` (keadaan terakhir) dan bagian "Belum dikerjakan" di bawahnya.
2. Jalankan tes di atas untuk memastikan kondisi dasar sehat.
3. Keputusan desain dan alasannya ada di `docs/changelog.md`; alur dan titik penyambungan ada di `docs/architecture.md`.

## Konfigurasi (`.env`)

| Variabel | Default | Fungsi |
|---|---|---|
| `DATABASE_URL` | `sqlite:///./hackx.db` | Koneksi DB (ganti untuk PostgreSQL/MySQL) |
| `CONTROL_LIVE_MODE` | `false` | `false` = perintah hanya dicatat (`dry_run`); `true` = dikirim lewat adapter perangkat |
| `MQTT_ENABLED` | `false` | `true` = backend tersambung ke broker MQTT dan memakai adapter MQTT |
| `MQTT_HOST` / `MQTT_PORT` | `127.0.0.1` / `1883` | Alamat broker |
| `MQTT_USERNAME` / `MQTT_PASSWORD` | kosong | Akun `engine` dari `deploy/mosquitto/credentials.txt` |
| `MQTT_TOPIC_PREFIX` | `smartx` | Prefix topik |
| `LOCAL_LOCK_SECONDS` | `120` | Lama prioritas fisik setelah tombol dosen (LOCAL) |
| `EMPTY_DELAY_SECONDS` | `20` | Jeda nol beruntun sebelum rule mematikan perangkat; demo 20 detik, produksi dapat memakai 300 detik |
| `VISION_STALE_SECONDS` | `6` | Umur maksimum pesan vision sebelum status UNKNOWN; data pulih memulai ulang timer okupansi |
| `ON_MIN_PERSONS` | `1` | Jumlah orang minimum untuk auto ON |
| `ON_DELAY_SECONDS` | `2` | Durasi okupansi minimum sebelum auto ON; `0` = langsung |
| `PREVIEW_URL` | kosong | URL fallback CCTV global (HLS `.m3u8` atau halaman pemutar MediaMTX); kamera per ruang diatur lewat Admin |
| `ADMIN_TOKEN` | kosong | Token untuk POST `/occupancy`, POST `/commands`, dan `/admin/*` (header `X-Admin-Token`); kosong = endpoint mutasi ditolak |

Catatan: dengan `CONTROL_LIVE_MODE=false`, `state` perangkat tidak berubah, jadi efek aturan tidak terlihat di dashboard. Ubah ke `true` untuk demo. Tanpa `MQTT_ENABLED=true`, adapter perangkat adalah simulasi dan tidak ada perangkat fisik yang tersentuh.

## Menjalankan dengan perangkat (MQTT)

```bash
cd deploy/mosquitto && ./setup.sh && docker compose up -d    # butuh Docker; membuat akun broker, sandi di credentials.txt (tidak ikut repository)
# isi .env: MQTT_ENABLED=true, MQTT_HOST=<IP laptop>, MQTT_USERNAME=engine, MQTT_PASSWORD=...
# lalu CONTROL_LIVE_MODE=true setelah perangkat tersambung
uvicorn app.main:app --host 127.0.0.1    # 127.0.0.1 jika dashboard hanya dibuka di laptop ini
```

Cek `GET /health`: `mqtt_connected` harus `true`. Format topik dan payload ada di [docs/mqtt-contract.md](docs/mqtt-contract.md). Endpoint mutasi HTTP memakai `ADMIN_TOKEN`; endpoint GET dashboard masih terbuka. Jangan buka API ke jaringan yang tidak dipercaya.

## Cara kerja singkat

1. `POST /occupancy` menerima `{room_id, person_count}` dengan header `X-Admin-Token`; kiriman vision lewat MQTT tetap memakai autentikasi broker.
2. Jika `person_count >= ON_MIN_PERSONS` terus-menerus selama `ON_DELAY_SECONDS`, lampu dan AC aktif yang belum menyala dinyalakan. Jika okupansi tetap 0 selama `EMPTY_DELAY_SECONDS`, perangkat yang `on` dimatikan. Pembacaan di bawah ambang mereset timer terkait; data stale (`VISION_STALE_SECONDS`) menjadi UNKNOWN dan tidak memicu ON maupun OFF.
3. Setiap perintah (otomatis maupun manual lewat `POST /commands`) tersimpan di tabel `commands` dengan sumber, status, alasan, dan waktu, dibaca lewat `GET /commands`.

Penjelasan lengkap dan diagram alur ada di [docs/architecture.md](docs/architecture.md).

## Struktur proyek

```
app/
├── main.py            # aplikasi FastAPI, pendaftaran router, penyajian frontend di /ui/
├── api/               # endpoint: occupancy, devices, commands, dashboard, preview, schedules, admin, auth
├── schemas/           # skema request/response (Pydantic)
├── models/            # tabel (SQLAlchemy): room, device, camera, occupancy, command, schedule, daily_usage, hourly_usage
├── services/          # logika kontrol, energi, jadwal contoh, kalender, ringkasan penggunaan, MQTT handler, ack tracker
├── adapters/          # penghubung luar: device_adapter, occupancy_adapter, mqtt_bridge
└── db/                # session.py (koneksi, pengaturan), seed.py (data demo), migrate.py (tambah kolom baru ke DB lama)
frontend/              # index.html, css/, js/ (modul ES), vendor/hls.min.js, tests/ (node --test); disajikan di /ui/
simulator/             # occupancy_simulator.py (skenario demo), device_simulator.py (perangkat via MQTT)
scripts/               # hardware_test.py: pengamat MQTT untuk tes perangkat asli
deploy/mosquitto/      # broker MQTT: docker-compose, ACL, setup.sh
tests/                 # tes pytest (DB in-memory)
docs/                  # dokumentasi
archive/               # salinan lama index.html frontend (riwayat, tidak dipakai aplikasi)
```

