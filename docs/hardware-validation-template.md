# Lembar Uji Perangkat Fisik

**Status:** template persiapan, belum ada hasil uji fisik.

| Informasi | Isian |
|---|---|
| Tanggal dan waktu uji | [isi] |
| Ruang / `room_id` | [isi] |
| Perangkat / `device_id` | [isi] |
| P3 (dashboard/backend) | [nama operator] |
| P4 (aktuator) | [nama operator] |
| Mode kontrol | [live / simulasi] |
| Versi firmware | [isi] |

## 1. Control Success

**Rumus:** `jumlah aksi fisik yang sesuai (x) / jumlah perintah uji terkirim (y) × 100%`.

Masukkan ke penyebut hanya perintah uji yang benar-benar dipublish ke perangkat. `dry_run`, gagal publish, dan perintah yang belum terkirim dicatat terpisah. Masukkan ke pembilang hanya perintah dengan aksi fisik yang benar-benar dilihat P4. Pesan state/ack saja tidak membuktikan lampu atau aktuator benar-benar berubah.

| No. | `cmd_id` | Aksi diminta | Waktu publish (UTC) | Hasil fisik yang diharapkan | Hasil yang dilihat P4 | Sesuai? | Catatan |
|---:|---|---|---|---|---|---|---|
| 1 | [isi] | [ON/OFF] | [isi] | [lampu/aktuator menyala atau mati] | [isi] | [Ya/Tidak] | [isi] |
| 2 | [isi] | [ON/OFF] | [isi] | [lampu/aktuator menyala atau mati] | [isi] | [Ya/Tidak] | [isi] |
| 3 | [isi] | [ON/OFF] | [isi] | [lampu/aktuator menyala atau mati] | [isi] | [Ya/Tidak] | [isi] |
| 4 | [isi] | [ON/OFF] | [isi] | [lampu/aktuator menyala atau mati] | [isi] | [Ya/Tidak] | [isi] |

**Rekap:** benar `[x]` / terkirim `[y]` = `[x ÷ y × 100]%`  
**Target lulus yang disepakati:** `[isi; jangan diasumsikan]`

## 2. Response Time

Ukur dari perubahan okupansi yang diterima backend sampai state perangkat kembali dengan `last_cmd_id` yang cocok. Catat semua waktu memakai jam server P3 dalam UTC. Waktu total mencakup jeda aturan: ON menunggu `ON_DELAY_SECONDS` (default 2 detik); OFF menunggu `EMPTY_DELAY_SECONDS` (default 20 detik).

| No. | Perubahan okupansi | Waktu diterima P3 `T_occ` (UTC) | `cmd_id` / `T_cmd` (UTC) | `last_cmd_id` / state / `T_ack` (UTC) | `T_ack − T_occ` | Catatan / konfirmasi fisik P4 |
|---:|---|---|---|---|---:|---|
| 1 | [mis. 0 → 1 orang] | [isi] | [isi] | [isi] | [isi detik] | [isi] |
| 2 | [mis. 1 → 0 orang] | [isi] | [isi] | [isi] | [isi detik] | [isi] |
| 3 | [isi] | [isi] | [isi] | [isi] | [isi detik] | [isi] |

**Rata-rata:** `[isi] detik`  
**Rentang minimum–maksimum:** `[isi]–[isi] detik`

`T_ack` harus berasal dari pesan `smartx/panel/{device_id}/state` yang diterima P3 dan membawa `last_cmd_id` sama dengan `cmd_id`. Gunakan satu jam P3 untuk timestamp okupansi, command, dan state agar selisih jam laptop tidak masuk ke hasil.

### Batas pengukuran saat ini

- Dashboard menyimpan `detected_at` okupansi. Namun, `last_changed_at` perangkat dan `executed_at` command dapat mencatat waktu command dikirim, bukan waktu perangkat membalas. Jangan memakai kedua field itu sebagai `T_ack`.
- Untuk response time, P3 perlu memberi timestamp saat pesan `state` diterima (misalnya dari monitor MQTT yang berjalan di laptop P3). P4 perlu mengonfirmasi aksi fisik untuk setiap `cmd_id`.
- Jika P4 tidak berada di jaringan yang dapat mencapai broker hotspot P3, pengujian fisik belum dapat dilakukan jarak jauh. Uji simulasi/dashboard boleh dilakukan, tetapi tidak dihitung sebagai Control Success perangkat fisik.
- Jika AC hanya menampilkan status pada OLED dan belum mengendalikan unit AC, catat sebagai uji tampilan/status, bukan aksi fisik AC.

## Data yang diminta dari P4

Sebelum uji, kirim pemetaan `room_id` ↔ `device_id` dan jenis aktuator. Untuk setiap baris uji, P4 mengirim `cmd_id`, aksi yang benar-benar terlihat, serta konfirmasi apakah state yang dilaporkan firmware muncul setelah aktuator berubah. Bila pengujian tertunda, isi firmware version dan status koneksi terlebih dahulu.

## Manfaat bisnis yang diharapkan

- **Efisiensi operasional:** petugas dapat melihat hubungan okupansi dan respons perangkat untuk membantu pemeriksaan ruang.
- **Pemanfaatan ulang infrastruktur:** dashboard, broker, kamera, ESP32, dan aktuator yang tersedia dapat dipakai bersama.
- **Potensi penghematan energi:** otomatisasi dapat mengurangi waktu perangkat menyala saat ruang kosong; nilainya belum diklaim dan perlu diukur dari data uji/pemakaian nyata.

Manfaat di atas adalah ekspektasi, bukan hasil yang sudah dibuktikan oleh template ini.
