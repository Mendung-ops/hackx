# Skrip demo

Alur demo sekitar 5 menit: kelas terisi lalu bubar, perangkat mati otomatis, riwayat bisa ditelusuri, lalu perintah manual dari dashboard. Semua langkah memakai `curl` atau `/docs`, jadi tidak butuh simulator maupun hardware. Alternatif visual: buka dashboard di `http://127.0.0.1:8000/ui/`, masuk ke Admin memakai token, lalu kirim okupansi 0 tiga kali lewat kartu Simulasi okupansi.

## Persiapan (sebelum demo)

1. Atur `ADMIN_TOKEN` dan `CONTROL_LIVE_MODE=true` di `.env` (supaya `state` perangkat benar-benar berubah; adapter-nya masih simulasi).
2. Reset data dummy:
   ```bash
   rm -f hackx.db
   python -m app.db.seed
   ```
3. Jalankan server:
   ```bash
   uvicorn app.main:app --reload
   ```
4. Buka `http://127.0.0.1:8000/docs` sebagai cadangan jika `curl` bermasalah.

## Langkah demo

### 1. Kondisi awal
```bash
curl -s localhost:8000/dashboard/overview
```
Tunjukkan: `live_mode: true`, `total_devices_on: 6`, `total_power_watt_now: 3060.0`. Tiga kelas, masing-masing lampu dan AC menyala.

### 2. Kelas terisi
```bash
curl -s -X POST localhost:8000/occupancy -H 'Content-Type: application/json' -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"room_id": 1, "person_count": 25}'
```
Tunjukkan: `commands` kosong. Ada orang, jadi tidak ada aksi.

### 3. Kelas bubar (kosong selama 20 detik)
Kirim pembacaan nol berkala selama setidaknya `EMPTY_DELAY_SECONDS` (default 20 detik), dengan jeda antarpesan tidak lebih dari `VISION_STALE_SECONDS` (default 6 detik). Contoh berikut mengirim tiap 2 detik selama 20 detik:
```bash
for i in $(seq 1 11); do
  curl -s -X POST localhost:8000/occupancy -H 'Content-Type: application/json' -H "X-Admin-Token: $ADMIN_TOKEN" \
    -d '{"room_id": 1, "person_count": 0}'
  if [ "$i" -lt 11 ]; then sleep 2; fi
done
```
Tunjukkan: perintah `commands` tetap kosong selama jeda belum tercapai; setelah 20 detik beruntun, dua perangkat menerima `turn_off` dengan `source: "rule"` dan `status: "sent"`.

Poin yang disampaikan: sistem menunggu nol berkelanjutan selama 20 detik. Deteksi positif langsung mengulang timer; jika kamera berhenti lebih dari 6 detik, status menjadi UNKNOWN dan tidak ada OFF.

### 4. Hasilnya di dashboard
```bash
curl -s localhost:8000/dashboard/overview
```
Tunjukkan: Kelas A101 `devices_on: 0`, total turun menjadi `total_devices_on: 4` dan `total_power_watt_now: 2040.0`.

### 5. Jejak alur kontrol
```bash
curl -s "localhost:8000/commands?limit=5"
```
Tunjukkan: setiap perintah tercatat dengan sumber (`rule`), alasan ("ruang kosong ≥20 detik (deteksi nol berkelanjutan)"), status, dan waktunya.

### 6. Perintah manual dari dashboard
```bash
curl -s -X POST localhost:8000/commands -H 'Content-Type: application/json' -H "X-Admin-Token: $ADMIN_TOKEN" \
  -d '{"device_id": 1, "action": "turn_on", "reason": "dosen masuk lebih awal"}'
```
Tunjukkan: `source: "manual"`, `status: "sent"`. Cek `curl -s localhost:8000/devices/1` untuk melihat `state: "on"`.

### 7. (Opsional) Mode dry-run
Set `CONTROL_LIVE_MODE=false`, restart server, reset data seperti di persiapan, lalu ulangi langkah 3. Tunjukkan: perintah tercatat dengan `status: "dry_run"` tetapi `state` perangkat tetap `on`. Poin: aturan bisa diuji dulu tanpa menyentuh perangkat sungguhan, dan perintah yang sama tidak menumpuk walau pembacaan kosong terus datang.

## Pertanyaan yang mungkin muncul

| Pertanyaan | Jawaban singkat |
|---|---|
| Saklar kelas benar-benar mati? | Lewat adapter. Sekarang masih simulasi; protokol asli cukup menambah satu kelas `send()` tanpa mengubah logika lain |
| Kalau deteksi salah atau kamera berhenti? | Satu deteksi positif mengulang timer kosong 20 detik; data yang berhenti lebih dari 6 detik menjadi UNKNOWN dan tidak memicu OFF. Semua perintah tetap tercatat untuk audit |
| Perangkat gagal merespons? | Perintah berstatus `failed` dengan alasan tercatat, `state` tidak berubah, dicoba lagi di pembacaan berikutnya |
| Perhitungan karbon? | Ada: `GET /dashboard/energy` (kWh, kgCO2, estimasi penghematan; faktor emisi 0,87 kgCO2/kWh, perlu diverifikasi ke ESDM) |

## Reset setelah demo
```bash
rm -f hackx.db && python -m app.db.seed
```
