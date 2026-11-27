# Catatan serah terima sesi (21 Okt 2026)

> Dokumen historis per 21 Okt 2026. Keadaan terkini ada di `docs/changelog.md`; cara menjalankan proyek ada di `README.md` dan `docs/HOW_TO_RUN.md`. Beberapa rujukan (jumlah tes, commit lokal, jalur berkas di komputer penulis) sudah tidak berlaku.

Untuk sesi Claude berikutnya yang **tidak tahu apa pun** tentang pekerjaan ini. Baca seluruh file ini, lalu `docs/changelog.md` (entri v0.5.0, v0.5.1, v0.6.0). Klaim di sini hanya yang sudah dibaca langsung di kode atau dikatakan user; yang belum terbukti ditandai.

## 1. Aturan kerja dari user
- Bahasa Indonesia.
- **Konsultasi dulu sebelum membangun**: ajukan rancangan, tunggu persetujuan, kerjakan bertahap.
- **Perintah yang bisa berjalan lama jangan dijalankan Claude** (uvicorn, pytest penuh, unduhan, docker). Berikan ke user untuk dijalankan. Membaca file, grep, dan edit file kecil lewat Desktop Commander boleh.
- **Catat semua perubahan di `docs/changelog.md`** (terbaru di atas, format: tanggal, versi, apa, mengapa).
- Sandi dan kredensial tidak boleh ditampilkan di chat: jangan buka `deploy/mosquitto/credentials.txt`, jangan minta user menempel sandi.
- User membuka folder repo dengan env conda `hackx` sudah aktif, jadi beri perintah singkat (`uvicorn app.main:app --host 127.0.0.1`, `python -m pytest -q`).
- Claude punya akses ke repo lewat Desktop Commander (muat dengan `tool_search`). Sandbox Claude tidak punya internet.

## 2. Sistem ini untuk apa
Hackathon SmartX, Case D "Smart Classroom Energy & Occupancy". Kamera YOLOv8 menghitung orang per ruang. Jika `person_count >= ON_MIN_PERSONS` (default 1) berlanjut selama `ON_DELAY_SECONDS` (default 2 detik), lampu dan AC aktif yang belum menyala dinyalakan; jika `person_count=0` berlanjut selama `EMPTY_DELAY_SECONDS` (default 20 detik), perangkat dimatikan. Data kamera yang lebih tua dari `VISION_STALE_SECONDS` (default 6 detik) menjadi UNKNOWN dan tidak memicu ON/OFF. Tombol fisik dosen (`last_cmd_id=LOCAL` + turn_on) mengunci OFF dari rule selama 120 detik. Pengguna target dashboard: **petugas fasilitas/energi** yang ingin tahu apakah ruang terjadwal sedang dipakai, memeriksa saran lampu/AC, dan melihat energi.

Stack: FastAPI + SQLAlchemy + SQLite (`hackx.db`) + paho-mqtt. Python 3.13 (env conda `hackx` atau venv). Dokumen: `README.md`, `docs/architecture.md`, `api-spec.md`, `mqtt-contract.md`, `changelog.md`.

## 3. Status git dan tes
- 4 commit lokal, belum di-push. **Belum diketahui apakah user sudah commit perubahan v0.5.1 dan v0.6.0**: jalankan `git status` dan `git log --oneline` dulu.
- Perubahan sesi ini (mungkin belum ter-commit): `app/services/mqtt_handler.py`, `tests/test_mqtt_handler.py`, `docs/mqtt-contract.md`, `docs/architecture.md`, `README.md`, `docs/changelog.md`, `frontend/index.html`, dan file ini.
- Tes: 42 lulus (dijalankan user setelah v0.5.1). v0.6.0 hanya mengubah frontend, tes belum dijalankan ulang.

## 4. Yang sudah selesai
- **Rule engine**: jeda kosong berbasis waktu, status UNKNOWN saat kamera basi, dry-run/live, retry untuk perintah `failed`.
- **Kunci prioritas fisik**: masa kunci diturunkan dari tabel `commands` (tahan restart), per perangkat, hanya `turn_on` LOCAL yang mengunci, hanya OFF dari rule yang diblokir (OFF manual lolos). Dua lapis: `evaluate_rules` dan `execute_command` (`PhysicalLockActive`, HTTP 409).
- **v0.5.1**: event `panel/{id}/event` LOCAL yang retained kini diabaikan (sebelumnya bisa memulai kunci baru saat reconnect). State retained sudah ditangani sejak awal.
- **MQTT**: `adapters/mqtt_bridge.py`, `services/mqtt_handler.py` (`ts` perangkat diabaikan, waktu = waktu terima server). Kontrak di `docs/mqtt-contract.md` sudah dikirim ke tim hardware (versi sebelum v0.5.1; isi topik/field tidak berubah, hanya ada kalimat tambahan "tanpa retain untuk tombol fisik").
- **Broker** `deploy/mosquitto` (container `smartx-mosquitto`; akun vision/panel/acunit/engine): lolos uji lokal. Pelajaran: setelah `setup.sh`, selalu `docker compose up -d --force-recreate`.
- **Hotspot laptop**: profil nmcli `hackx-hotspot`, SSID `HACKX-NET`, antarmuka `wlp2s0`, band `bg` (2,4 GHz), IP `10.42.0.1/24`, status aktif saat dicek. `autoconnect` belum dipastikan.
- **UI v0.6.0** (`frontend/index.html`, ditulis ulang): layar ringkasan (`#/`) dan detail ruang (`#/ruang/{id}`), denah simulasi sebagai pengganti kamera, grafik riwayat okupansi, riwayat perintah per ruang, `safe()` per endpoint. Sintaks JS lolos `node --check`, **tetapi Claude belum melihatnya di browser dan user belum memberi umpan balik tampilan**. Versi lama bisa dikembalikan dengan `git checkout frontend/index.html` (hanya jika versi lama sudah ter-commit).

## 5. Belum selesai: integrasi di venue (jam acara belum diketahui)
1. `.env`: `MQTT_ENABLED=true`, `MQTT_USERNAME=engine`, `MQTT_PASSWORD` (user isi sendiri), `MQTT_HOST=<IP laptop>`; `CONTROL_LIVE_MODE=true` hanya setelah perangkat tersambung; `PREVIEW_URL`.
2. **Jaringan utama belum diputuskan.** Masalah: satu kartu Wi-Fi tidak bisa jadi hotspot sekaligus online, sedangkan laptop dipakai bekerja. Opsi: hotspot HP sebagai jaringan utama (IP broker berubah), dongle USB Wi-Fi atau kabel/tethering untuk internet (IP `10.42.0.1` tetap). Pertanyaan tertunda: apakah di venue ada port LAN atau dongle?
3. **Uji broker dari perangkat lain belum pernah dilakukan.** ufw aktif; Docker bisa melewati ufw, jadi hanya tes dari perangkat lain yang valid. Usul: `sudo ufw allow from 10.42.0.0/24 to any port 1883 proto tcp`, lalu `mosquitto_pub -h 10.42.0.1 -p 1883 -t test -m x` dari HP (tanpa kredensial harus "not authorised").
4. **Pesan ke tim hardware belum dikirim**: kontrak terbaru, daftar ID, alamat broker, akun dikirim terpisah; minta firmware kirim state sekali saat tersambung, **tanpa retain untuk tombol fisik**, dan dua SSID cadangan.
5. Tarik image Docker dan cek jam laptop sebelum acara. Jalankan `uvicorn app.main:app --host 127.0.0.1`, cek `GET /health`.
6. **Live preview**: teman user menyediakan MediaMTX; format yang diminta sudah dijawab **HLS**. Menunggu dari teman: URL HLS lengkap, IP yang terjangkau dari browser (bukan localhost), apakah path berlogin (saran: tanpa login tetapi dibatasi IP, atau akun baca-saja), CORS (`hlsAllowOrigin`), satu stream atau per ruang. `PREVIEW_URL` belum diisi. **Pemutar HLS belum ada di frontend**; hls.js harus disimpan lokal di `frontend/vendor/hls.min.js` (user perlu mengunduhnya sendiri, mis. `curl` dari jsdelivr hls.js 1.5.x; versi belum diverifikasi). `/preview` hanya punya satu URL; jika kamera per ruang, perlu diubah.
7. API tidak berautentikasi: uvicorn di `127.0.0.1` menutupnya tetapi perangkat lain tidak bisa membuka dashboard. Alternatif: `--host 0.0.0.0` + ufw hanya untuk IP tertentu pada port 8000.

## 6. Permintaan user untuk UI (inti pekerjaan berikutnya)
- Alur: ringkasan semua ruang, lalu pilih ruang, lalu detail (okupansi dll) plus preview yang merepresentasikan CCTV. (Sudah dibuat di v0.6.0 dengan denah simulasi.)
- **UI tidak boleh menampilkan info MQTT dan LIVE/DRY-RUN**, dan umumnya tidak boleh menampilkan info yang tidak relevan dengan tujuan awal sistem. **v0.6.0 masih menampilkan lencana MQTT, lencana LIVE/DRY-RUN, catatan DRY-RUN di detail ruang, dan peringatan LIVE di panel simulasi. Semuanya harus dibuang.** Cukup peringatan kecil "data tidak terbarui" jika API tidak terjangkau.
- Angka (perangkat menyala, energi, dll) seharusnya bisa berubah juga di dry-run. Saat ini dry-run tidak mengubah state dan energi hanya dihitung dari perintah berstatus `sent`, jadi angka tetap 0. Diusulkan mode ketiga "simulasi" (state berubah, status perintah khusus, DB terpisah lewat `DATABASE_URL`, tidak memublish MQTT). **Belum diputuskan user.** Jika UI nanti tidak menampilkan mode, ini tetap perlu agar demo tanpa perangkat bisa berjalan.
- **Halaman admin** untuk menentukan kondisi awal ruangan: jumlah sakelar per ruang; satu sakelar biasanya menyalakan 3 lampu; skema ruang berbeda-beda. Data saat ini: 1 "Lampu" (120 W) + 1 "AC" (900 W) per ruang, tidak ada konsep jumlah lampu. Rancangan yang diajukan (belum disetujui eksplisit): satu sakelar = satu baris `devices`; tambah kolom `lamp_count`; `power_watt` = jumlah lampu x watt per lampu (perhitungan energi tidak berubah); `ADMIN_TOKEN` di `.env` untuk endpoint admin; migrasi `ALTER TABLE devices ADD COLUMN lamp_count INTEGER NOT NULL DEFAULT 1` (cadangkan `hackx.db` dulu; `create_all` tidak menambah kolom); menonaktifkan perangkat, bukan menghapus; kunci prioritas tetap per sakelar; ID perangkat baru harus diberitahukan ke tim hardware dan dicatat di `docs/mqtt-contract.md`. **Pertanyaan tertunda: apakah tiap sakelar punya modul panel ESP32 sendiri (ID MQTT sendiri)?**

## 7. Prototipe user sebagai acuan UI
- `06-Prototype/index.html` dan `Prototype.md` dari folder SmartX-Hackathon-Discovery milik user (berkas lokal di luar repository; dibuat user dengan GPT, rancangan awal, data sintetis). `dashboard/index.html` di folder yang sama adalah pemilih kasus hackathon, **abaikan**.
- Prototipe memuat: pilih ruang (201/202); status ruang (jadwal, terpantau kosong/terisi, lama tanpa aktivitas); suhu; energi hari ini; kamera ilustrasi dengan overlay deteksi dan toggle; jejak energi dengan pilih tanggal-waktu dan rentang (tahun, bulan, minggu, hari, jam, menit); kartu rekomendasi ("ruang terjadwal tapi kosong, lampu OFF dan AC ECO", petugas yang menerapkan); status kontrol.
- Hasil perbandingan dengan UI kita (sudah disampaikan ke user):
  - **Belum ada**: jadwal ruang (tidak ada datanya di backend), lama kosong (bisa dihitung dari `GET /occupancy`, tanpa ubah backend), energi per ruang (`GET /dashboard/energy?room_id=` sudah ada), grafik energi dengan rentang waktu (butuh endpoint deret waktu baru; data nyata hanya ada sejak sistem berjalan, jadi usul hanya menit/jam/hari), kartu rekomendasi.
  - **Jangan ditampilkan dulu**: suhu (tidak ada sensornya di kontrak MQTT).
  - **Ketidakcocokan**: (1) prototipe advisory, backend kita otomatis; usul kartu rekomendasi menampilkan status tindakan otomatis ("Kosong sejak 09:42, lampu dimatikan otomatis"), bukan tombol terapkan; (2) prototipe menyebut "AC ECO", kontrak kita hanya on/off; (3) overlay deteksi butuh koordinat kotak, kontrak MQTT hanya membawa `person_count`, jadi hanya mungkin jika stream teman sudah beranotasi YOLO (tanyakan ke dia); (4) video asli menampilkan wajah, prototipe menekankan tanpa identitas.
  - **Karbon**: `Prototype.md` menyatakan tidak menghitung penghematan karbon tanpa baseline energi dan faktor emisi tervalidasi. Faktor 0,87 kita belum diverifikasi ke ESDM. Usul: sembunyikan "Emisi dihindari", "Hemat", dan kartu karbon dari UI utama; label energi sebagai estimasi (daya terpasang x lama menyala, bukan meter).
  - Kartu "alur pengguna utama" dan label "data simulasi" milik prototipe tidak perlu dibawa.
- **Pertanyaan tertunda: apakah jadwal ruang perlu ada (input manual per ruang di halaman admin) agar status "terjadwal tapi kosong" bisa tampil, atau cukup kosong/terisi tanpa jadwal?**

## 8. Urutan kerja yang diusulkan (belum disetujui user)
1. Bersihkan UI (buang MQTT/mode/karbon/simulasi dari halaman detail), tambah lama kosong, energi per ruang, kartu rekomendasi. Tanpa ubah backend.
2. Halaman admin (sakelar dan jumlah lampu, ADMIN_TOKEN, migrasi), tes, dokumen, changelog.
3. Grafik energi (endpoint deret waktu baru).
4. Pemutar HLS (setelah URL dari teman ada dan hls.js tersimpan lokal).
5. Mode simulasi untuk angka energi tanpa perangkat (jika user setuju).

## 9. Celah dan keputusan terbuka lain
`AckTracker` belum dipasang (perintah berstatus `sent` begitu dipublish); MQTT tanpa TLS; `chmod 640` file acl; semua perangkat di `hackx.db` awalnya "off" sampai melapor state; aturan nyalakan otomatis belum diputuskan; faktor emisi 0,87 belum diverifikasi ke ESDM; skema DB tim (seed hanya aman dijalankan ke DB yang tidak dipakai bersama); kontrak topik/ID harus dijaga konsisten dengan firmware.

## 10. Langkah pertama sesi berikutnya
1. Baca file ini dan `docs/changelog.md`; jalankan `git status` dan `git log --oneline`.
2. Tanyakan ke user: bagaimana tampilan UI v0.6.0 di browser; jawaban dua pertanyaan tertunda (jadwal ruang? tiap sakelar punya modul sendiri?); satu stream atau per ruang; jaringan utama di venue.
3. Mulai dari langkah 1 di bagian 8, setelah rancangan disetujui.
