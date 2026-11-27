# Changelog dan catatan keputusan

Urutan terbaru di atas. Setiap perubahan yang memengaruhi alur, kontrak API, atau skema data dicatat di sini beserta alasannya. Tambahkan entri baru di bagian atas setiap kali ada perubahan.

Format entri: tanggal, versi, apa yang berubah, dan **mengapa**.

---

## 2026-11-27 · (dokumentasi) · Persiapan repository GitHub
- Menulis ulang panduan mulai cepat di `README.md` (prasyarat, clone, venv, `.env`, seed, URL lokal), menambah `docs/HOW_TO_RUN.md` (konfigurasi, database, layanan eksternal, pemecahan masalah), dan menyesuaikan struktur proyek di README dengan isi repo. Perintah tes menjadi `python -m pytest` tanpa `-q`.
- `.gitignore` diperluas: `.env.*` (kecuali `.env.example`), `hackx.db.bak*`, berkas SQLite (`-journal`, `-wal`, `-shm`), `node_modules/`, log, dan berkas editor/OS.
- `hackx.db` dan 7 berkas `hackx.db.bak-*` tidak disertakan ke repository: data uji dari pengembangan (termasuk alamat jaringan lokal kamera) dan dapat dibuat ulang lewat `python -m app.db.seed` serta seed otomatis saat server mulai. Riwayat git lama (yang memuat cadangan tersebut) tidak ikut diunggah; repository baru dimulai dari satu commit bersih.
- `docs/handoff.md`: jalur berkas lokal penulis dibuang dan diberi catatan bahwa dokumen bersifat historis.
- Tidak ada perubahan kode aplikasi, skema data, API, atau kontrak MQTT.
- **Mengapa:** repository dibuat untuk dibagikan ke rekan tim; harus bisa dijalankan setelah clone tanpa berkas lokal atau data uji.

## 2026-10-22 · v0.13.2 · Login CCTV sementara untuk mode dev
- Form Admin menerima username dan password HTTP Basic terpisah dari URL. Preview memakai proxy backend same-origin agar browser tidak meminta kredensial.
- Kredensial hanya berada di memori server, tidak tersimpan di SQLite, log, atau respons API, dan hilang saat server dimulai ulang. Admin dapat menghapusnya sebelum restart. Proxy menolak redirect ke origin atau jalur lain.
- **Mengapa:** dialog autentikasi browser mengganggu pratinjau CCTV, sementara penyimpanan password permanen tidak diperlukan untuk demo mode dev.

## 2026-10-22 · v0.13.1 · Pesan validasi kamera yang terbaca
- Admin kini menerjemahkan detail validasi kamera HTTP 422 menjadi pesan Bahasa Indonesia yang menunjukkan field bermasalah, termasuk ketidakcocokan ID CCTV dengan segmen path URL.
- Form kamera memberi placeholder dan petunjuk URL http/https tanpa kredensial. Login kamera tetap dimasukkan melalui dialog browser saat preview dibuka, dan tidak disimpan aplikasi.
- Tes mereproduksi URL berkredensial, ID yang tidak ada di path, URL tanpa path, dan URL RTSP; tes juga memastikan URL MediaMTX maupun `.m3u8` valid tersimpan, muncul di daftar Admin, dan dibaca `/preview`.
- **Mengapa:** sebelumnya detail Pydantic berupa daftar objek diringkas menjadi teks `422`, sehingga admin tidak tahu bagian input yang harus diperbaiki.

## 2026-10-22 · v0.13.0 · Auto turn-on okupansi
- Menambahkan auto ON untuk lampu dan AC aktif: `person_count >= ON_MIN_PERSONS` harus berkelanjutan selama `ON_DELAY_SECONDS` sebelum engine mengirim `turn_on` dengan source `engine`; delay 0 berarti langsung.
- Timer positif memakai waktu terima server UTC, berhenti pada pembacaan di bawah ambang atau celah stale, dan tidak memicu ketika ruang `UNKNOWN`. State perangkat serta perintah engine terakhir mencegah perintah berulang; MQTT tetap menghasilkan `cmd_id` unik.
- Konfigurasi baru `ON_MIN_PERSONS=1` dan `ON_DELAY_SECONDS=2`; enum source API/OpenAPI bertambah `engine`, tetapi source itu hanya internal. Schema DB dan topic/payload MQTT tidak berubah. OFF 20 detik, fail-safe 6 detik, dan lock fisik 120 detik tetap berlaku.
- **Mengapa:** perangkat dapat menyala otomatis setelah okupansi dikonfirmasi, tanpa bereaksi pada deteksi singkat atau saat kamera basi.

## 2026-10-22 · v0.12.0 · Rule kosong berbasis durasi dan fail-safe vision
- Mengganti syarat tiga pembacaan nol dengan `EMPTY_DELAY_SECONDS` (default 20 detik). Nol pertama memulai timer; deteksi positif atau celah data lebih lama dari `VISION_STALE_SECONDS` langsung meresetnya.
- Menambahkan status internal `UNKNOWN` saat tidak ada pesan occupancy lebih dari `VISION_STALE_SECONDS` (default 6 detik). UNKNOWN tidak mengirim OFF; setelah data pulih timer kosong dimulai ulang. OFF manual tetap tidak terblokir oleh kunci tombol fisik.
- Menambahkan clock yang dapat diinjeksi di service okupansi dan memakai timestamp terima server UTC. Kontrak topik/payload MQTT tidak berubah; OpenAPI version menjadi 0.12.0.
- Tes diperbarui untuk flicker, batas 19/20 detik, kamera basi dan pemulihan, konfigurasi environment, serta lock LOCAL 120 detik. Changelog dan dokumentasi aturan dikoreksi.
- **Mengapa:** deteksi YOLO dapat hilang sesaat; durasi kosong mengabaikan flicker, sementara status UNKNOWN memastikan kamera mati tidak pernah dianggap sebagai ruang kosong.

## 2026-10-22 · v0.11.0 · Ringkasan penggunaan keseluruhan
- Menambah `hourly_usage` dan memperluas `daily_usage` dengan menit serta energi saat ruang kosong. Riwayat contoh 26 minggu tetap deterministik dan kini memiliki profil jam serta pemborosan 5–25%.
- Menambah `GET /dashboard/usage-overview?period=7d|30d|6m` untuk perbandingan periode, energi, okupansi, utilisasi jadwal, peringkat ruang, dan heatmap jam sibuk.
- Dashboard mendapat halaman `#/ringkasan` dengan grafik tren, kartu perubahan, tabel ruang yang bisa diurutkan, heatmap jam, dan kalender penggunaan yang sudah ada.
- Data measured memakai okupansi nyata dan interval status ON/OFF dari histori perintah yang sama dengan estimator energi. Energi idle hanya dihitung ketika ruang terdeteksi kosong dan setidaknya satu perangkat ON.
- DB lama perlu dicadangkan lalu dimigrasikan sebelum server dijalankan: `python -m app.db.migrate`. Rule engine, kunci fisik, dan logika kontrol perangkat tidak berubah.
- Tes belum dijalankan sesuai instruksi sesi; jalankan `python -m pytest -q` setelah migrasi dan pencadangan DB.

## 2026-10-22 · v0.10.0 · Jadwal kelas dan kalender penggunaan
- Menambah tabel `schedules` untuk jadwal mingguan per ruang dan `daily_usage` untuk ringkasan harian. Tabel baru dibuat lewat `create_all`; tidak ada ALTER tabel lama. Database lokal perlu dicadangkan sebelum menjalankan seed, migrasi, atau server.
- Admin dapat mengelola jadwal (tambah, edit, hapus, aktif/nonaktif), mengisi jadwal contoh, dan mengisi riwayat contoh. Seed jadwal memilih ruang A101/A102/A103 berdasarkan nama atau fallback urutan ID, serta idempoten.
- Dashboard menampilkan jadwal mingguan ruang, jadwal sekarang/berikutnya, dan heatmap kontribusi 26 minggu dengan metrik jam terisi, energi, atau jam terjadwal. Klik tanggal membuka ringkasan dan daftar sesi. Kalender tersedia untuk semua ruang atau satu ruang.
- Riwayat contoh deterministik mengisi tanggal yang belum ada. Pembacaan okupansi non-sintetis memperbarui tanggal menjadi `measured`; durasi okupansi dipotong pada ambang basi dan batas hari lokal. Energi dihitung ulang melalui `energy_service.summarize()`.
- Jadwal hanya menjadi informasi dan rekomendasi UI; `event_service`, `control_service`, kunci fisik, dan logika kontrol perangkat tidak memakai jadwal.
- **Mengapa:** petugas dapat membandingkan pemakaian aktual dengan jadwal ruang dan melihat pola lintas ruang tanpa mengubah perilaku perangkat.
- Tes belum dijalankan sesuai instruksi sesi; jalankan `python -m pytest -q` setelah mencadangkan database.

## 2026-10-22 · v0.9.1 · Dashboard, autentikasi mutasi, dan kontrak fail-safe
- Frontend dipisah menjadi `frontend/app.js` dan `frontend/style.css`; beranda mengurutkan ruang yang butuh perhatian, menampilkan waktu pembaruan, dan meredupkan data saat API gagal. Polling turun menjadi 10 detik, berhenti saat tab tersembunyi, dan riwayat okupansi beranda memakai satu endpoint `/occupancy/recent`.
- Simulasi okupansi dipindah ke panel Admin. `POST /occupancy` dan `POST /commands` kini memerlukan `X-Admin-Token`; tombol kontrol meminta login, memberi konfirmasi saat ruang masih terisi, dan menampilkan sumber/aksi perintah dalam bahasa yang mudah dibaca.
- Preview memakai hls.js lokal untuk HLS, menampilkan status memuat, dan hanya menerima URL kamera `http(s)` tanpa kredensial. Tiga backup HTML dipindah ke `archive/frontend/`.
- Batas umur okupansi backend diselaraskan menjadi **6 detik** dengan status UNKNOWN di UI. Data basi tidak boleh memicu OFF; jadwal resmi belum terintegrasi dan harus diikuti petugas secara manual.
- Kontrak perangkat: QoS 1; `state` dan `status` retained, `cmd`, `event`, dan PIR tidak retained. PIR bersifat telemetri saja. AC v1 tetap `turn_on`/`turn_off`; `setback`/`temp` belum diimplementasikan.
- **Mengapa:** mencegah halaman statis terlihat kosong saat ada error, mengurangi request berulang, membatasi endpoint yang mengubah perangkat, serta menjaga lampu tetap menyala bila kamera berhenti mengirim.

## 2026-10-21 · v0.9.0 · Kelengkapan kelas, kontrol per switch, dan multi-CCTV
- Admin dapat menambah dan mengedit kelas, switch lampu/AC, serta beberapa kamera dalam satu kelas. Setiap kamera menyimpan nama, ID CCTV, URL sumber, dan status aktif; ID CCTV wajib menjadi segmen jalur URL, misalnya `kelas-demo-01` pada `http://10.124.223.85:8889/kelas-demo-01/`.
- Satu entri perangkat mewakili satu switch/relay dan dapat mengendalikan sebagian lampu. Admin menyimpan jumlah unit dan watt per unit; daya switch dihitung otomatis (`jumlah × watt per unit`). Contoh: 3 lampu × 12 W = 36 W. Energi per jam ialah `daya total (W) × jam menyala ÷ 1000`, jadi 36 W selama 1 jam = 0,036 kWh.
- Halaman kelas menampilkan feed CCTV aktif sebagai kartu terpisah beserta ID dan tautan sumber. Dashboard tetap menampilkan tombol kontrol terpisah untuk tiap switch.
- Migrasi menambah `devices.unit_count`, `devices.watt_per_unit`, dan tabel `cameras`, lalu menyalin konfigurasi CCTV lama dari `rooms` ke tabel kamera. Database SQLite dicadangkan sebelum perubahan.
- **Mengapa:** pembagian lampu berdasarkan jalur relay memungkinkan kontrol parsial seperti mematikan 3 dari 9 lampu; kamera dan konsumsi daya dapat dicatat sesuai kondisi tiap kelas.

## 2026-10-21 · v0.8.2 · Preview CCTV kelas dan konfigurasi sumber di Admin
- Halaman detail ruang menampilkan live preview per `room_id`: URL pemutar dan ID CCTV dibaca dari `/preview`; halaman MediaMTX seperti `http://10.124.223.85:8889/kelas-demo-01/` disematkan sebagai iframe, sedangkan URL `.m3u8` ditampilkan sebagai video.
- Admin kini meminta `ADMIN_TOKEN`, lalu menyediakan input ID CCTV dan URL sumber per ruang melalui `PATCH /admin/rooms/{id}`. Pasangan ID/URL wajib diisi bersama atau dikosongkan bersama untuk menghapus konfigurasi. Token disimpan hanya pada `sessionStorage` tab tersebut.
- Dokumentasi API, konfigurasi fallback `PREVIEW_URL`, dan README diperbarui.
- **Mengapa:** tiap kelas dapat memakai stream CCTV dan ID kamera sendiri; URL global hanya menjadi fallback ketika ruang belum dikonfigurasi.
- Migrasi `python -m app.db.migrate` sudah dijalankan pada `hackx.db` lokal (backup dibuat otomatis); jalankan juga pada database lama lain yang belum memiliki kolom `rooms.camera_id` dan `rooms.camera_url`.

---

## 2026-10-21 · v0.8.1 · Tes menampilkan progres per tes
- Menambah `pytest.ini`: `addopts = -v --tb=short` dan `testpaths = tests`. Setiap tes kini tampil dengan nama, hasil (PASSED/FAILED), dan persentase progres; kegagalan ditampilkan ringkas.
- Perintah tes menjadi `python -m pytest` (tanpa `-q`, karena `-q` membatalkan `-v` dan kembali ke titik-titik). `README.md` disesuaikan. Tidak ada perubahan pada kode aplikasi atau isi tes.
- Ditambah `--color=yes` di `pytest.ini` agar PASSED hijau dan FAILED merah selalu tampil (pytest hanya mewarnai otomatis jika keluarannya terdeteksi sebagai terminal).

---

## 2026-10-21 · v0.8.0 · Admin backend: ruang, sakelar lampu, AC (tahap 1 dari 2)
- **Skema `devices`** bertambah 5 kolom: `switch_code`, `lamp_count`, `watt_per_lamp`, `module_note`, `active` (default `true`). `power_watt` lampu = `lamp_count x watt_per_lamp`, jadi perhitungan energi tidak berubah.
- **Migrasi:** `python -m app.db.migrate` (file baru `app/db/migrate.py`) hanya menambah kolom yang belum ada, aman diulang, dan mencadangkan `hackx.db` ke `hackx.db.bak-<waktu>` lebih dulu. Wajib dijalankan sekali pada `hackx.db` yang sudah ada (`create_all` tidak menambah kolom). DB baru dari seed/tes tidak perlu.
- **Endpoint `/admin/*`** (`app/api/admin.py`, skema `app/schemas/admin.py`): ruang (daftar, buat, ubah) dan perangkat (daftar, buat, ubah). Dilindungi header `X-Admin-Token` = `ADMIN_TOKEN` di `.env` (setting baru; kosong = `503`). Respons perangkat memuat `topics` MQTT (command/state/event) sesuai `docs/mqtt-contract.md`. Detail di `docs/api-spec.md`.
- **Perangkat nonaktif (`active=false`):** dilewati rule engine, `POST /commands` ditolak `409` (`DeviceInactive` di `control_service.py`), tidak tampil di `/dashboard/overview`. Tidak ada endpoint hapus: riwayat perintah tetap utuh.
- **`GET /devices` dan `/dashboard/overview`** menambah field opsional `switch_code`, `lamp_count`, `watt_per_lamp`, `module_note`, `active` (tidak merusak klien lama).
- **Tes:** `tests/test_admin.py` (12 tes). Jumlah di `README.md` diubah 46 menjadi 58; **dijalankan user: 58 lulus**.
- **Keputusan:** (1) satu sakelar atau satu AC = satu perangkat = satu ID MQTT; sakelar A yang menyalakan 3 lampu adalah 1 perangkat dengan `lamp_count=3`. (2) `room_id` dan `type` tidak bisa diubah setelah dibuat karena ID/jenis tertanam di firmware. (3) Kolom ESP32 tidak dimodelkan; hanya `module_note` bebas, karena backend hanya butuh ID. (4) Perangkat baru berstatus `unknown` sampai melapor state.
- **Batasan:** (1) energi historis dihitung dengan `power_watt` terbaru, jadi mengubah jumlah lampu ikut mengubah angka energi masa lalu perangkat itu. (2) Energi perangkat nonaktif tetap ikut dihitung (riwayatnya masih ada). (3) Belum ada log audit di tabel; perubahan admin hanya tercatat di log server (`hackx.admin`). (4) Layar admin di frontend belum ada (tahap 2).
- **Tindak lanjut:** ID perangkat baru harus dikirim ke tim hardware.

---

## 2026-10-21 · v0.7.2 · Jadwal dummy untuk uji kamera mati (hanya UI)
- `frontend/index.html`: menambah `DUMMY_SCHEDULE` (A101: 08:00-12:00 dan 13:00-17:30, A102: 09:00-11:00, A103: 15:00-18:00) dan `scheduleNow()`. Saat kartu ruang berstatus "Tidak diketahui", teks rekomendasi kini menyebut hasil jadwal: ada kelas (perangkat sebaiknya tetap menyala) atau tidak ada kelas (petugas diminta memeriksa dan mematikan manual bila kosong). Judul kartu: "Tidak diketahui · jadwal: ada kelas/tidak ada kelas".
- Untuk uji di jam berapa pun: buka dashboard dengan `?jadwal=ada` atau `?jadwal=kosong` di URL.
- **Keputusan: jadwal dummy hanya di UI, backend tidak berubah.** Alasan: data jadwal ruang asli belum ada; ini hanya agar skenario kamera P4 dimatikan bisa diuji. Jadwal bersifat saran tampilan, **tidak** memicu tindakan otomatis (lampu tetap tidak dimatikan saat UNKNOWN).
- Sintaks JS lolos `node --check`; belum diuji di browser.

## 2026-10-21 · v0.7.1 · Fail-safe kamera mati (backend dan UI)
- **Backend:** `services/event_service.py` `_room_is_empty` kini juga memeriksa umur pembacaan. Ketiga pembacaan 0 terakhir wajib terjadi dalam `EMPTY_READING_MAX_AGE_SECONDS` (default **30 dtk**, `0` = nonaktif; pengaturan baru di `app/db/session.py` dan `.env.example`). Tes baru: `tests/test_stale.py` (4 tes). Tes lain tidak diubah.
- **UI:** `frontend/index.html`: `STALE_MS` dari 120000 menjadi **6000**. Jika pembacaan terakhir lebih tua dari itu, kartu ruang menampilkan "Tidak diketahui" (angka orang "–", denah "Kamera tidak terbaca", kalimat "sistem tidak mengambil tindakan otomatis"), bukan terisi/kosong. Kalimat peringatan lama dihapus. Kartu kembali normal otomatis begitu pembacaan baru masuk. Backend tidak berubah untuk bagian ini.
- **Mengapa:** sebelumnya dua nol lama + satu nol baru (setelah kamera mati lama) dihitung tiga pembacaan kosong berturut-turut dan mematikan lampu/AC padahal selama kamera mati kondisi ruang tidak diketahui. UI juga menulis "kosong/terisi" seolah pasti saat data basi.
- **Batasan:** (1) 30 dtk di backend mengasumsikan jeda kirim kamera di bawah 15 dtk; bila lebih lambat, naikkan nilainya (aturan = 2 x jeda + cadangan). (2) 6 dtk di UI mengasumsikan jeda kirim kamera di bawah sekitar 3 dtk; UI memuat ulang tiap 3 dtk, jadi UNKNOWN muncul 6 sampai 9 dtk setelah kamera berhenti. (3) "Ikut jadwal" belum ada: backend tidak punya data jadwal ruang. (4) Jam browser dan server harus sama (dashboard dibuka di laptop yang sama dengan backend).
- Jumlah tes di `README.md`: 42 menjadi 46 (belum dijalankan; user menjalankan `python -m pytest -q`).

## 2026-10-21 · v0.7.0 · UI: bersihkan, lama kosong, energi per ruang, kartu rekomendasi (langkah 1)
- `frontend/index.html` diubah; **backend dan kontrak API tidak berubah**. Cadangan versi sebelumnya: `frontend/index.v0.6.0.bak.html` (hapus jika tidak perlu).
- **Dibuang dari UI:** lencana MQTT, lencana LIVE/DRY-RUN, catatan DRY-RUN, kartu emisi/hemat/emisi dihindari beserta catatan faktor emisi, dan pemilih jendela energi. Status perintah `dry_run` ditampilkan sebagai "tercatat". Sebagai gantinya satu lencana kecil "Data tidak terbarui" bila API tidak terjangkau atau sebagian endpoint gagal.
- **Ditambah:** (1) lama kosong, dihitung dari deret pembacaan `GET /occupancy` (per ruang, 300 terakhir; "lebih dari" bila seluruh data adalah nol); (2) energi hari ini per ruang, dijumlahkan dari `devices[].room_id` di `GET /dashboard/energy?start=<00:00 setempat>`, diberi label estimasi; (3) kartu rekomendasi per ruang: ruang dipakai, kosong n dari 3 pembacaan, kosong dan perangkat sudah dimatikan otomatis (pukul berapa), ruang terisi tetapi perangkat mati, dikendalikan langsung di ruangan (kunci tombol fisik), dan peringatan data okupansi lebih dari 2 menit.
- **Simulasi okupansi dipindah** ke layar `#/admin` (tautan kecil di kaki halaman) dengan pemilih ruang. Layar ini disiapkan untuk langkah 2 (sakelar dan jumlah lampu).
- Nilai aturan di UI ditulis tetap (`EMPTY_N=3`, `LOCK_S=120`): harus disamakan bila `EMPTY_READINGS_REQUIRED` atau `LOCAL_LOCK_SECONDS` berubah. Kunci fisik dideteksi dari perintah `local` `turn_on` di `GET /commands`, bukan field backend.
- Parameter `start` energi kini dikirim sebagai UTC tanpa zona (sesuai konvensi API); sebelumnya memakai akhiran `Z`.
- **Mengapa:** angka dan label yang tidak berhubungan dengan tujuan sistem (mode, MQTT, karbon yang faktornya belum tervalidasi) dibuang; petugas fasilitas perlu melihat ruang terjadwal kosong, saran tindakan, dan energi pendukung. Rekomendasi menjelaskan tindakan otomatis dan peran manusia (tombol fisik, tombol manual), bukan tombol "terapkan".
- Belum diuji di browser; sintaks JS lolos `node --check`.

## 2026-10-21 · docs · Catatan serah terima
- Menambah `docs/handoff.md`: ringkasan untuk sesi berikutnya (aturan kerja, status, yang belum selesai di venue, permintaan UI dan admin, hasil perbandingan dengan prototipe user, pertanyaan tertunda, langkah pertama). Tidak ada perubahan kode.

## 2026-10-21 · v0.6.0 · Dashboard dua layar (langkah 1)
- `frontend/index.html` ditulis ulang. **Layar 1 (`#/`)**: lencana mode dan status MQTT, ringkasan total (perangkat menyala, daya, kWh, kgCO₂, hemat), dan kartu per ruang yang bisa diklik (Terisi/Kosong, jumlah orang, status lampu dan AC, daya). **Layar 2 (`#/ruang/{id}`)**: panel "Kamera" berupa denah simulasi (satu titik per orang), jumlah orang besar dengan grafik riwayat (`GET /occupancy`), perangkat dengan tombol nyalakan/matikan, riwayat perintah khusus ruang itu, dan panel "Simulasi okupansi" yang terlipat.
- Status MQTT diambil dari `GET /health` (`mqtt_enabled`, `mqtt_connected`). Setiap endpoint diambil terpisah (`safe()`), jadi satu galat tidak lagi mengosongkan seluruh halaman.
- Waktu di tabel kini memakai jam setempat (sebelumnya UTC).
- Tanpa perubahan backend dan kontrak API. Tanpa dependensi eksternal (tidak ada CDN).
- **Belum ada:** pemutar video HLS (panel kamera masih denah simulasi), lencana "terkunci" prioritas fisik (butuh field baru di `/dashboard/overview`), dan mode simulasi untuk angka energi.
- **Mengapa:** satu halaman panjang sulit dibaca di depan penonton; alur "ringkasan semua ruang, lalu pilih ruang, lalu detail" lebih mudah diikuti. Kolom kirim okupansi dipindah ke panel terlipat agar tidak tersentuh tak sengaja.
- Pembaruan dokumen kecil: jumlah tes di `README.md` dan `docs/architecture.md` dikoreksi menjadi 42.

## 2026-10-21 · v0.5.1 · Event LOCAL yang retained tidak lagi memulai kunci
- `services/mqtt_handler.py`: pesan `panel/{id}/event` dengan `last_cmd_id=LOCAL` yang berstatus retained sekarang diabaikan (dicatat di log level info), sama seperti topik `state`.
- Tes: menambah `test_event_local_retained_tidak_memulai_lock` di `tests/test_mqtt_handler.py`; penekanan non-retained tetap mengunci.
- Dokumentasi: `docs/mqtt-contract.md` (butir 3 perilaku backend) dan `docs/architecture.md` (bagian prioritas fisik) diperbarui: retained pada `state` hanya sinkron state, pada `event` diabaikan; firmware diminta tidak memakai retain untuk tombol fisik.
- **Mengapa:** sebelumnya hanya topik `state` yang menolak retained. Jika firmware mem-publish event tombol dengan retain, setiap reconnect backend memutar ulang pesan itu dan memulai kunci 120 dtk baru, sehingga lampu bisa tertahan menyala tanpa ada yang menekan tombol. Catatan: tim hardware tetap diminta tidak memakai retain untuk tombol fisik.

## 2026-10-21 · v0.5.0 · MQTT, prioritas fisik, live preview, rapikan dokumentasi
- Menambah jembatan MQTT: `adapters/mqtt_bridge.py` (subscribe data perangkat, publish perintah ke `smartx/cmd/{device_id}`, Last Will `smartx/status/engine`) dan `services/mqtt_handler.py` (menerjemahkan pesan menjadi aksi rule engine). Aktif jika `MQTT_ENABLED=true`.
- Menambah broker Mosquitto di `deploy/mosquitto/` (akun `vision`, `panel`, `acunit`, `engine` dengan ACL; `setup.sh` membuat sandi acak).
- Menambah prioritas fisik: laporan `last_cmd_id=LOCAL` + turn_on mengunci OFF dari rule selama `LOCAL_LOCK_SECONDS` (default 120). Setelah kunci habis, hitungan "ruang kosong" dimulai dari nol.
- Menambah `GET /preview` (URL HLS dari MediaMTX lewat `PREVIEW_URL`) dan `simulator/device_simulator.py` (simulasi panel, acunit, vision lewat MQTT).
- Menambah `services/ack_tracker.py` (pelacak ack, murni logika). **Belum dipasang ke bridge**; timeout bawaan 0 (nonaktif).
- Tes: 41 lulus (`test_mqtt_handler.py`, `test_local_lock.py` ditambahkan).
- **Keputusan: `ts` dari perangkat diabaikan; semua waktu adalah waktu terima server.** Alasan: ESP32 di venue tidak punya NTP.
- **Keputusan: rule engine tidak tahu MQTT.** Bridge hanya meneruskan pesan ke `mqtt_handler` dan menjadi `DeviceAdapter`. Alasan: logika aturan tetap bisa dites tanpa broker.
- **Keputusan: masa kunci diturunkan dari riwayat tabel `commands`**, bukan kolom baru. Alasan: tidak mengubah skema DB bersama dan tetap utuh setelah server restart.
- **Keputusan: pesan retained tidak memulai kunci baru.** Alasan: replay saat reconnect bukan penekanan tombol baru.
- **Keputusan: kontrak topik ditetapkan backend** (`docs/mqtt-contract.md`); perangkat yang menyesuaikan.
- Dokumentasi: menambah `docs/mqtt-contract.md`; memperbarui README, `.env.example`, `docs/api-spec.md` (`/health`, `/preview`, sumber `local`, error 409), dan `docs/architecture.md` (alur MQTT, prioritas fisik, konfigurasi).
- Catatan keamanan: API HTTP belum memakai autentikasi dan MQTT berjalan tanpa TLS; untuk acara, jalankan uvicorn pada `127.0.0.1` jika dashboard hanya dibuka di laptop backend.

## 2026-10-19 · v0.4.0 · Tahap 7: frontend
- Menambah `frontend/index.html` (satu file, HTML/JS murni tanpa build) dan menyajikannya di `/ui/` lewat `StaticFiles`; `/` dialihkan ke `/ui/`.
- Dashboard menampilkan: mode live/dry-run, ringkasan (perangkat menyala, daya, kWh, kgCO₂, penghematan), kartu per ruang dengan tombol nyalakan/matikan, kolom kirim okupansi per ruang (menggantikan simulator saat demo), dan 15 perintah terakhir. Data diperbarui tiap 3 detik; jendela energi bisa 15 menit, 1 jam, atau 24 jam.
- **Keputusan: frontend disajikan dari origin yang sama dengan API.** Alasan: tidak perlu CORS dan tidak perlu langkah build; cukup `uvicorn`.
- Menambah 1 tes (`test_frontend_disajikan`), total 27 tes.

## 2026-10-19 · v0.3.1 · Tes otomatis dan simulator
- Menambah `tests/` (26 tes, DB SQLite in-memory): `test_control.py` (perintah, dry-run, aturan ruang kosong), `test_api.py` (alur penuh lewat HTTP), `test_energy.py` (perhitungan kWh/penghematan). Jalankan: `python -m pytest -q`.
- Mengisi `simulator/occupancy_simulator.py`: tiga skenario (`kelas-bubar`, `deteksi-goyah`, `semua-ruang`) yang mengirim data ke `POST /occupancy`.
- `simulator/device_simulator.py` dibiarkan kosong; perangkat disimulasikan oleh `SimulatedDeviceAdapter`.
- **Alasan:** aturan kontrol dan perhitungan energi sudah menjadi inti demo, jadi perlu pengaman sebelum frontend dan adapter asli ditambahkan.
- Catatan: tanpa riwayat perintah, `/dashboard/energy` menganggap perangkat menyala sepanjang jendela jika state-nya `on`. Pada DB seed baru, angka kWh 24 jam terlihat besar; ini asumsi, bukan pengukuran.

## 2026-10-19 · v0.3.0 · Tahap 6: energi dan karbon
- Menambah `services/energy_service.py`, `schemas/energy.py`, dan endpoint `GET /dashboard/energy` (kWh, kgCO2, estimasi penghematan per perangkat dan total).
- Menambah `emission_factor_kg_per_kwh` (default 0,87, sistem Jamali) dan `emission_factor_source` di `Settings`.
- **Keputusan: energi dihitung dari riwayat perintah berstatus `sent`**, dengan daya perangkat konstan saat ON. Penghematan = lama perangkat mati setelah perintah `rule` turn_off, dibanding andai tetap menyala.
- **Catatan:** faktor emisi perlu diverifikasi ke nilai ESDM terbaru sebelum disitasi.

## 2026-10-19 · v0.2.0 · Tahap 5: API
- Menambah endpoint `/occupancy`, `/devices`, `/commands`, `/dashboard/overview` dan mendaftarkannya di `main.py`.
- Menambah skema `OccupancyResult`, `RoomOverview`, `DashboardOverview`.
- Menulis dokumentasi (`README.md`, `docs/*`).
- **Alasan:** semua alur bisa dicoba dari `/docs` tanpa kode tambahan; riwayat perintah dibuka lewat `GET /commands` supaya alur kontrol bisa ditelusuri.
- Catatan: dengan `CONTROL_LIVE_MODE=false`, aturan "ruang kosong" hanya menghasilkan perintah `dry_run`, `state` perangkat tidak berubah, jadi overview tidak ikut berubah.

## 2026-10-19 · v0.1.x · Tahap 4: lapisan kontrol
- Menambah `adapters/device_adapter.py` (antarmuka `DeviceAdapter` + `SimulatedDeviceAdapter`), `adapters/occupancy_adapter.py`, `services/control_service.py`, `services/event_service.py`.
- Aturan pertama: ruang kosong → matikan perangkat yang masih `on`.
- **Keputusan: ruang dianggap kosong setelah 3 pembacaan terakhir berturut-turut 0 orang** (`EMPTY_READINGS_REQUIRED`). Alasan: satu deteksi 0 bisa salah dan tidak boleh mematikan lampu/AC saat kelas berlangsung.
- **Keputusan: aturan hanya mematikan, belum menyalakan otomatis.** Alasan: perilaku menyalakan perlu diputuskan oleh pemilik proyek.
- **Keputusan: adapter perangkat disimulasikan dulu.** Alasan: protokol saklar asli belum diputuskan; antarmuka `send()` membuat penggantinya tidak mengubah kode lain.
- **Keputusan: dry-run tidak mengubah `state`, dan perintah `dry_run` tidak menumpuk.** Alasan: dry-run harus aman dan hasil catatannya tidak membengkak.

## 2026-10-19 · v0.1.x · Pembersihan
- Mengganti `datetime.utcnow()` (deprecated) dengan `utcnow()` di `app/db/session.py`, dipakai oleh model dan seed.
- **Alasan:** menghilangkan peringatan deprecation dan memusatkan sumber waktu di satu tempat.

## 2026-10-19 · v0.1.x · Keputusan DB dummy
- **Keputusan: memakai DB dummy (SQLite lokal `hackx.db`) untuk sementara**, bukan DB teman setim.
- **Alasan:** pengembangan tidak perlu menunggu skema DB bersama. Pindah nanti cukup mengganti `DATABASE_URL` dan menyesuaikan `app/models/*` jika kolomnya berbeda.
- Seed (`python -m app.db.seed`): 3 ruang (Kelas A101–A103), tiap ruang 1 lampu (120 W) dan 1 AC (900 W), semua `on`. Aman dijalankan berulang.

## 2026-10-19 · v0.1.x · Tahap 3: skema dan seed
- Menambah skema Pydantic di `app/schemas/` dan `app/db/seed.py`.

## 2026-10-19 · v0.1.x · Tahap 2: model
- Menambah model `Room`, `Device`, `OccupancyRecord`, `Command`.
- **Keputusan: tabel `commands` mencatat setiap perintah** (sumber, status, alasan, waktu). Alasan: prioritas utama proyek adalah alur yang bisa dilacak.
- **Keputusan: layanan hanya memakai nama atribut Python, bukan nama kolom.** Alasan: jika tabel DB teman setim berbeda, cukup ubah `app/models/*`.
- Tabel tidak dibuat otomatis saat aplikasi start, hanya lewat seed manual, supaya tidak bentrok dengan DB bersama.

## 2026-10-19 · v0.1.0 · Tahap 1: fondasi
- Menambah `requirements.txt`, `.env.example`, `.gitignore`, `app/db/session.py`, `app/main.py` (`/health`).
- Struktur folder `hackx/` dibuat sesuai rancangan, ditambah `__init__.py` di tiap paket dan `.gitkeep` di folder kosong.
- **Keputusan: `CONTROL_LIVE_MODE` default `false`.** Alasan: aman untuk dites; perangkat hanya tersentuh jika sengaja dinyalakan.

---

## Belum dikerjakan
- Aturan menyalakan otomatis saat ada orang masuk (belum diputuskan).
- Uji dengan firmware ESP32 dan kamera YOLOv8 asli di venue (kontrak: `docs/mqtt-contract.md`).
- Memasang `AckTracker` ke bridge, lalu mengaktifkan `MQTT_ACK_TIMEOUT_SECONDS` setelah firmware terbukti mengirim ack.
- Autentikasi API HTTP (API key) jika dashboard dibuka dari perangkat selain laptop backend.
- Skema DB tim (sekarang masih SQLite dummy).
