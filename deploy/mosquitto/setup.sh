#!/usr/bin/env bash
# Buat akun broker (vision, panel, acunit, engine, monitor) dengan sandi acak.
# Hasil: passwd (dibaca broker) dan credentials.txt (sandi teks biasa, jangan di-commit).
# Jalankan sekali: ./setup.sh && docker compose up -d
set -euo pipefail
cd "$(dirname "$0")"

mkdir -p data
printf 'UID=%s\nGID=%s\n' "$(id -u)" "$(id -g)" > .env

# Jika `docker compose up` pernah jalan sebelum setup.sh, Docker membuat `passwd`
# sebagai DIREKTORI milik root dan broker crash-loop (exit 139). Hapus lewat container.
if [ -d passwd ]; then
  docker run --rm --user 0 -v "$PWD":/c --entrypoint rm eclipse-mosquitto:2 -rf /c/passwd
fi
rm -f passwd

: > credentials.txt
first=1
for u in vision panel acunit engine monitor; do
  pw=$(openssl rand -base64 18 | tr -d '/+=' | cut -c1-16)
  # -b: sandi dari argumen (tanpa prompt); -c: buat file baru, hanya untuk akun pertama
  flags="-b"; [ "$first" = 1 ] && flags="-c -b" && first=0
  docker run --rm --user "$(id -u):$(id -g)" -v "$PWD":/c eclipse-mosquitto:2 \
    mosquitto_passwd $flags /c/passwd "$u" "$pw"
  echo "$u:$pw" >> credentials.txt
done
chmod 600 passwd credentials.txt
echo "OK. Sandi ada di $PWD/credentials.txt"
