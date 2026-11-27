# Cara menjalankan HackX

Panduan lengkap untuk menjalankan HackX setelah `git clone`. Ringkasan singkatnya ada di [README.md](../README.md); dokumen ini menambahkan detail konfigurasi, database, layanan eksternal, dan pemecahan masalah.

## Status verifikasi

Langkah di dokumen ini dijalankan pada 27 Nov 2026 dari salinan bersih repository (tanpa `.env`, tanpa `hackx.db`) di Linux dengan Python 3.13.16.

| Bagian | Status |
|---|---|
| `pip install -r requirements.txt` di venv baru | Terverifikasi |
| `python -m app.db.seed`, `python -m app.db.migrate` pada DB baru | Terverifikasi |
| `uvicorn app.main:app`: `/health`, `/ui/`, `/docs`, `/dashboard/*`, `/schedules`, `/admin/*` | Terverifikasi |
| POST `/occupancy` dengan dan tanpa `X-Admin-Token` | Terverifikasi (201 dan 401); `/admin/*` tanpa token memberi 503 |
| `python -m pytest` (107 tes) dan `node --test` di `frontend/` (4 tes) | Terverifikasi, semua lulus |
| `python -m simulator.occupancy_simulator --scenario kelas-bubar` terhadap server lokal | Terverifikasi |
| Sintaks `deploy/mosquitto/setup.sh` dan `docker-compose.yml` | Hanya sintaks yang diperiksa (`bash -n`, `docker compose config`); broker **belum dijalankan** dalam audit ini |
| MQTT dengan broker, perangkat ESP32, kamera YOLOv8, aliran CCTV MediaMTX | **Belum diverifikasi**; membutuhkan layanan atau perangkat eksternal (lihat di bawah) |
| Windows, macOS, Python selain 3.13, PostgreSQL/MySQL | **Belum diverifikasi** |

## 1. Prasyarat

- Git dan Python 3.13 (dengan modul `venv`).
- Opsional: Node.js (tes frontend), Docker (broker MQTT).
- Koneksi internet saat `pip install`.

## 2. Instalasi

```bash
git clone https://github.com/Mendung-ops/hackx.git
cd hackx
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Dependensi yang dipasang: FastAPI, Uvicorn, SQLAlchemy, Pydantic (+ pydantic-settings), python-dotenv, paho-mqtt, serta pytest dan httpx untuk tes dan simulator. Frontend tidak memerlukan build atau `npm install`: berkasnya statis dan disajikan oleh backend. `frontend/package.json` hanya dipakai untuk menjalankan `node --test`.

Jika Anda memakai conda, proyek ini sebelumnya dikembangkan dengan env `hackx` (Python 3.13); `python -m venv` cukup untuk pemakai lain.

## 3. Konfigurasi environment

```bash
cp .env.example .env
```

`.env` dibaca dari folder tempat perintah dijalankan, jadi jalankan semua perintah dari root repository. **Jangan commit `.env`** (sudah ada di `.gitignore`).

Untuk demo lokal tanpa perangkat, ubah dua nilai:

| Variabel | Nilai demo | Alasan |
|---|---|---|
| `ADMIN_TOKEN` | string acak, mis. dari `python -c "import secrets; print(secrets.token_urlsafe(32))"` | Kosong berarti halaman Admin dan endpoint POST (`/occupancy`, `/commands`, `/admin/*`) ditolak |
| `CONTROL_LIVE_MODE` | `true` | `false` hanya mencatat perintah sebagai `dry_run`, `state` perangkat tidak berubah sehingga efek aturan tidak terlihat |

Daftar lengkap variabel ada di [README.md](../README.md#konfigurasi-env). Pengaturan tambahan yang dikenali aplikasi (di `app/db/session.py`) tetapi tidak ada di `.env.example`:

| Variabel | Default | Fungsi |
|---|---|---|
| `MQTT_CLIENT_ID` | `engine` | ID klien MQTT backend |
| `MQTT_ACK_TIMEOUT_SECONDS` | `0` | Batas tunggu ack perangkat; `0` = nonaktif |
| `EMISSION_FACTOR_SOURCE` | teks sumber Jamali 0,87 | Keterangan sumber faktor emisi |

## 4. Database dan data demo

Aplikasi memakai SQLite (`hackx.db` di root repository, sesuai `DATABASE_URL=sqlite:///./hackx.db`). **File database dan cadangannya tidak ada di repository**: berisi data uji dari pengembangan dan dapat dibuat ulang dari kode.

```bash
python -m app.db.seed
```

Perintah ini membuat tabel dan mengisi 3 ruang (Kelas A101 sampai A103), masing-masing 1 lampu (120 W) dan 1 AC (900 W), semuanya berstatus `on`. Aman dijalankan berulang (idempotent). Saat server mulai, aplikasi juga mengisi otomatis (jika tabelnya kosong): 11 jadwal kuliah contoh, serta histori penggunaan dummy harian dan per jam selama 26 minggu untuk halaman **Ringkasan penggunaan**. Data dummy itu berlabel `dummy` dan digantikan data terukur untuk hari yang sama.

| Keperluan | Perintah |
|---|---|
| Reset ke kondisi demo awal | `rm -f hackx.db && python -m app.db.seed` |
| Meng-upgrade `hackx.db` lama ke skema terbaru | `python -m app.db.migrate` (hanya menambah kolom; SQLite dicadangkan otomatis ke `hackx.db.bak-<waktu>`) |
| Cadangan manual | `cp hackx.db hackx.db.bak-manual` |

Seed dan migrasi membuat tabel yang belum ada. **Jangan dijalankan ke database bersama (mis. milik tim) sebelum skemanya dicek.** Untuk PostgreSQL/MySQL, ubah `DATABASE_URL` dan aktifkan driver yang dikomentari di `requirements.txt`; jalur ini belum diverifikasi.

## 5. Menjalankan backend dan frontend

```bash
uvicorn app.main:app --reload
```

Tidak ada server frontend terpisah: backend menyajikan `frontend/` di `/ui/`.

| URL | Isi |
|---|---|
| http://127.0.0.1:8000/ui/ | Dashboard: daftar ruang |
| http://127.0.0.1:8000/ui/#/ruang/1 | Detail ruang (ganti angka dengan ID ruang) |
| http://127.0.0.1:8000/ui/#/penggunaan | Ringkasan penggunaan |
| http://127.0.0.1:8000/ui/#/admin | Admin: ruang, perangkat, kamera, jadwal (butuh `ADMIN_TOKEN`) |
| http://127.0.0.1:8000/docs | Swagger UI |
| http://127.0.0.1:8000/health | `{"status":"ok", ...}`, termasuk `live_mode` dan `mqtt_connected` |

Server hanya menerima koneksi dari komputer ini. Endpoint GET dashboard tidak berautentikasi, jadi jangan membuka API (`--host 0.0.0.0`) ke jaringan yang tidak dipercaya.

### Pemakaian pertama

1. Buka `/ui/#/admin`, masukkan nilai `ADMIN_TOKEN` dari `.env`. Token hanya disimpan di `sessionStorage` browser untuk sesi itu. Setelah masuk, kontrol perangkat di detail ruang aktif.
2. Kirim data okupansi lewat kartu **Simulasi okupansi** di halaman Admin atau lewat `curl`:
   ```bash
   curl -s -X POST localhost:8000/occupancy -H 'Content-Type: application/json' \
     -H "X-Admin-Token: $ADMIN_TOKEN" -d '{"room_id": 1, "person_count": 25}'
   ```
3. Alur demo 5 menit (kelas bubar lalu perangkat mati otomatis) ada di [demo-script.md](demo-script.md). Aturan: nol orang berlanjut selama `EMPTY_DELAY_SECONDS` (default 20 detik), dengan jarak antarpesan tidak lebih dari `VISION_STALE_SECONDS` (default 6 detik), baru mematikan perangkat.

## 6. Tes

```bash
python -m pytest                 # tanpa -q; DB in-memory, tidak menyentuh hackx.db
cd frontend && node --test       # tes modul frontend (router, store, scheduler)
```

## 7. Simulator

Simulator okupansi mengirim POST `/occupancy` ke server yang sedang berjalan:

```bash
export ADMIN_TOKEN=<nilai yang sama dengan .env>
python -m simulator.occupancy_simulator --scenario kelas-bubar   # juga: deteksi-goyah, semua-ruang
# opsi: --base-url http://127.0.0.1:8000  --delay <detik antar putaran>
```

Dengan `EMPTY_DELAY_SECONDS=20` dan `--delay 1` (default), skenario `kelas-bubar` belum membuat perangkat mati karena nolnya hanya berlangsung beberapa detik. Terverifikasi: dengan `EMPTY_DELAY_SECONDS=2` di server, dua perintah `turn_off` (sumber `rule`) tercatat pada pembacaan nol ketiga. `device_simulator` (meniru perangkat dan vision lewat MQTT) membutuhkan broker; lihat bagian berikut.

## 8. Bagian yang membutuhkan layanan, kredensial, atau perangkat eksternal

Demo lokal (bagian 2 sampai 7) berdiri sendiri. Fitur berikut **tidak bisa dijalankan hanya dari isi repository** dan belum diverifikasi dalam audit ini:

| Kebutuhan | Dipakai untuk | Catatan |
|---|---|---|
| Broker MQTT Mosquitto (Docker) | Komunikasi dengan perangkat nyata | Dibuat oleh `deploy/mosquitto/setup.sh`; butuh Docker dan `openssl`. Sandi akun (`vision`, `panel`, `acunit`, `engine`, `monitor`) dibuat acak dan ditulis ke `deploy/mosquitto/credentials.txt` (tidak ikut repository) |
| Modul ESP32 panel (lampu) dan acunit (AC) | Menerima perintah, melaporkan state | Firmware ada di luar repository. Kontrak topik dan payload: [mqtt-contract.md](mqtt-contract.md) |
| Kamera dengan YOLOv8 | Mengirim jumlah orang per ruang (`person_count`) lewat MQTT | Program deteksi ada di luar repository; tanpa itu gunakan simulator atau POST `/occupancy` |
| Aliran CCTV (mis. MediaMTX) | Live preview di detail ruang | URL kamera diatur per ruang di Admin, atau `PREVIEW_URL` sebagai cadangan global. URL harus `http(s)` tanpa username/password dan memuat ID CCTV sebagai satu segmen jalur (lihat [api-spec.md](api-spec.md)). Login HTTP Basic dimasukkan terpisah di Admin dan hanya disimpan di memori server selama berjalan. Pemutar HLS (`hls.js`) sudah ikut di `frontend/vendor/` |
| Database tim (PostgreSQL/MySQL) | Pengganti SQLite | Atur `DATABASE_URL` dan pasang driver; belum diuji |

Langkah broker, dari yang tertulis di `README.md` dan `deploy/mosquitto/setup.sh`:

```bash
cd deploy/mosquitto
./setup.sh                          # membuat passwd dan credentials.txt (jangan dibuka di chat atau di-commit)
docker compose up -d                # setelah menjalankan ulang setup.sh, pakai: docker compose up -d --force-recreate
cd ../..
# .env: MQTT_ENABLED=true, MQTT_HOST=<IP komputer ini>, MQTT_USERNAME=engine,
#       MQTT_PASSWORD=<sandi akun engine dari credentials.txt>
# CONTROL_LIVE_MODE=true hanya setelah perangkat tersambung
uvicorn app.main:app --host 127.0.0.1
curl -s localhost:8000/health       # mqtt_connected harus true
```

Catatan keamanan dari catatan serah terima: broker membuka port 1883 di semua antarmuka agar ESP32 dapat tersambung, tanpa TLS. Uji dari perangkat lain belum pernah dilakukan; jangan memakai jaringan yang tidak dipercaya. Docker dapat melewati aturan firewall `ufw`. Jangan memakai `credentials.txt`, `passwd`, atau `.env` di luar mesin Anda.

## 9. Pemecahan masalah

| Gejala | Penyebab dan solusi |
|---|---|
| `ModuleNotFoundError: No module named 'app'` | Jalankan dari root repository dan gunakan `python -m ...` atau `uvicorn app.main:app`. Pastikan venv aktif |
| `.env` tidak terbaca atau `hackx.db` muncul di folder lain | `.env` dan `sqlite:///./hackx.db` dibaca relatif terhadap folder kerja. Pindah ke root repository |
| `pip install` gagal | Pakai Python 3.13 (satu-satunya yang diverifikasi), venv baru, dan koneksi internet |
| `Address already in use` | Port 8000 terpakai: `uvicorn app.main:app --port 8001` dan ganti port di URL |
| Dashboard kosong, tidak ada ruang | Database belum diisi: `python -m app.db.seed` |
| Halaman Admin atau `/admin/*` memberi 503 | `ADMIN_TOKEN` di `.env` kosong. Isi lalu restart server |
| POST `/occupancy`, `/commands` memberi 401 | Header `X-Admin-Token` tidak ada atau tidak sama dengan `ADMIN_TOKEN` |
| Perintah tercatat `dry_run`, status perangkat tidak berubah | `CONTROL_LIVE_MODE=false`. Ubah ke `true` dan restart |
| Perangkat tidak mati setelah okupansi 0 | Rule menunggu nol berlanjut selama `EMPTY_DELAY_SECONDS` (20 detik), dan pesan yang lebih jarang dari `VISION_STALE_SECONDS` (6 detik) membuat status UNKNOWN tanpa OFF. Kirim nol tiap beberapa detik, atau turunkan `EMPTY_DELAY_SECONDS` untuk uji |
| Error kolom tidak ditemukan (`no such column`) pada DB lama | Skema DB tertinggal: `python -m app.db.migrate` (cadangan otomatis dibuat) |
| `mqtt_connected: false` di `/health` | Periksa `MQTT_ENABLED=true`, host/port, username dan sandi, serta broker berjalan (`docker compose ps` di `deploy/mosquitto`) |
| Broker Mosquitto crash berulang (exit 139) | `passwd` terbentuk sebagai direktori karena `docker compose up` dijalankan sebelum `setup.sh`. Jalankan ulang `./setup.sh` (menghapusnya lewat container), lalu `docker compose up -d --force-recreate` |
| Live preview kosong | Pastikan URL kamera terisi di Admin, bisa dijangkau dari browser (bukan hanya dari server), dan server MediaMTX mengizinkan asal halaman (CORS) |
| `node: command not found` saat tes frontend | Pasang Node.js, atau lewati tes frontend (opsional) |

## 10. Membersihkan

```bash
rm -f hackx.db hackx.db.bak-*     # hapus database lokal dan cadangannya
rm -rf .venv                       # hapus virtual environment
docker compose -f deploy/mosquitto/docker-compose.yml down   # hentikan broker, jika dijalankan
```
