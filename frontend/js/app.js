import { api, isAbortError } from "./api.js";
import { el } from "./dom.js";
import { appStore } from "./store.js";

const $ = (id) => document.getElementById(id);
const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const fmt = (n, d = 2) => Number(n).toLocaleString("id-ID", { maximumFractionDigits: d });
const toDate = (s) => (s instanceof Date ? s : s ? new Date(s + "Z") : null);
const clock = (s) => { const d = toDate(s); return d && !isNaN(d) ? d.toLocaleTimeString("id-ID", { hour12: false }) : "–"; };
const stamp = (s) => { const d = toDate(s); return d && !isNaN(d) ? d.toLocaleString("id-ID", { hour12: false }) : "–"; };
const dayStart = () => { const d = new Date(); d.setHours(0, 0, 0, 0); return d.toISOString().slice(0, 19); };
const ago = (ms) => {
  const m = Math.floor(ms / 60000);
  if (m < 1) return "kurang dari 1 menit";
  if (m < 60) return m + " menit";
  const h = Math.floor(m / 60), r = m % 60;
  return h + " jam" + (r ? " " + r + " menit" : "");
};

const EMPTY_N = 3, LOCK_S = 120, STALE_MS = 6000, OCC_LIMIT = 300;
let overview = null, health = null, energy = null, cmds = [], occBy = {}, errors = [];
let cameraPreview = null, cameraPreviewRoomId = null, cameraPreviewStatus = "idle";
let lastUpdatedAt = null, view = { name: "home" }, inFlight = false, refreshQueued = false;
const WEEKDAYS = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"];
let schedules = [], schedulesLoadedAt = 0, schedulesRequest = null, schedulesRequestId = 0, schedulesError = "";
let scheduleWeekOffset = 0;
const usageViews = {
  home: { metric: "occupancy", roomId: "", data: null, selectedDate: "" },
  room: { metric: "occupancy", roomId: null, data: null, selectedDate: "" },
  summary: { metric: "occupancy", roomId: "", data: null, selectedDate: "" },
};
let usageRequests = { home: null, room: null, summary: null };

async function safe(path) {
  try { return await api(path); } catch (e) { if (!isAbortError(e)) errors.push(e.message); return null; }
}
function adminToken() { return sessionStorage.getItem("hackx.adminToken") || ""; }
function setCameraLoading(roomId) {
  cameraPreview = null;
  cameraPreviewRoomId = roomId;
  cameraPreviewStatus = "loading";
  const box = $("r-preview");
  box.dataset.source = "loading";
  box.innerHTML = `<div class="camera-empty">Memuat feed CCTV…</div>`;
  $("r-camera-note").textContent = "Memuat konfigurasi kamera untuk ruang ini…";
}

export function handleRoute(nextView) {
  const previousView = view;
  schedulesRequestId += 1;
  schedulesRequest = null;
  for (const screen of Object.keys(usageRequests)) {
    if (!usageRequests[screen]) continue;
    usageViews[screen].requestId = (usageViews[screen].requestId || 0) + 1;
    usageRequests[screen] = null;
  }
  view = nextView;
  appStore.setState({ route: view });
  if (view.name === "room" && (previousView.name !== "room" || previousView.id !== view.id)) {
    usageViews.room.data = null; usageViews.room.key = ""; usageViews.room.selectedDate = "";
    usageViews.room.loadedAt = 0; scheduleWeekOffset = 0;
  }
  $("home").hidden = view.name !== "home";
  $("room").hidden = view.name !== "room";
  $("admin").hidden = view.name !== "admin";
  $("usage-overview").hidden = view.name !== "summary";
  $("not-found").hidden = view.name !== "not-found";
  if (view.name === "not-found") {
    $("not-found").replaceChildren(el("section", { className: "card", attrs: { role: "status" } }, [
      el("h2", { textContent: "Halaman tidak ditemukan" }),
      el("p", { textContent: "Alamat yang dibuka tidak tersedia. Kembali ke daftar ruang untuk melanjutkan." }),
      el("a", { textContent: "Kembali ke ruang", attrs: { class: "back", href: "#/" } }),
    ]));
  }
  document.querySelectorAll(".top-nav a").forEach((link) => {
    if (link.hash === location.hash) link.setAttribute("aria-current", "page");
    else link.removeAttribute("aria-current");
  });
  $("r-msg").textContent = "";
  if (view.name === "room") setCameraLoading(view.id);
  window.scrollTo(0, 0);
  if (view.name === "not-found") return;
  refresh();
  loadSchedules();
  if (view.name === "home" || view.name === "room" || view.name === "summary") loadUsageCalendar(view.name, true);
  if (view.name === "summary") window.UsageOverview?.onShow();
}

export async function loadApiVersion() {
  const label = $("app-version");
  if (!label) return;
  try {
    const specification = await api("/openapi.json", { routeScoped: false });
    label.textContent = specification.info?.version ? `Versi aplikasi ${specification.info.version}` : "Versi aplikasi tidak tersedia";
  } catch (_) {
    label.textContent = "Versi aplikasi tidak tersedia";
  }
}

const devLabel = (d) => (d.type === "light" ? "Lampu" : d.type === "ac" ? "AC" : d.name);
const isStale = (room) => !!room.last_detected_at && Date.now() - toDate(room.last_detected_at) > STALE_MS;
function scheduleNow(roomId, now = new Date()) {
  const override = new URLSearchParams(location.search).get("jadwal");
  if (override === "kosong") return null;
  if (override === "ada") return { title: "Jadwal contoh", end_time: "23:59", active: true };
  const day = (now.getDay() + 6) % 7;
  const minute = now.getHours() * 60 + now.getMinutes();
  return schedules.find((item) => item.room_id === Number(roomId) && item.active && item.day_of_week === day
    && minute >= timeMinutes(item.start_time) && minute < timeMinutes(item.end_time)) || null;
}
function timeMinutes(value) {
  const [hour, minute] = String(value || "0:0").split(":").map(Number);
  return hour * 60 + minute;
}
function emptyInfo(list) {
  if (!list || !list.length) return null;
  let k = 0;
  while (k < list.length && list[k].person_count === 0) k++;
  if (k === 0) return { empty: false };
  return { empty: true, count: k, since: list[k - 1].detected_at, truncated: k === list.length };
}
function advise(room) {
  const n = room.latest_person_count;
  const scheduled = scheduleNow(room.room.id);
  if (n === null) return { tone: "muted", title: "Belum ada data okupansi", text: "Rekomendasi muncul setelah kamera mengirim pembacaan." };
  if (isStale(room)) {
    const last = room.last_detected_at ? `Pembacaan terakhir pukul ${clock(room.last_detected_at)} (${ago(Date.now() - toDate(room.last_detected_at))} lalu). ` : "";
    const scheduleText = scheduled ? `Menurut jadwal ruang, ${scheduled.title} berlangsung sampai ${scheduled.end_time}. ` : "";
    return { tone: "warn", unknown: true, title: "Kondisi ruang tidak diketahui", text: `${last}${scheduleText}Jangan matikan perangkat berdasarkan data ini; sistem membiarkan perangkat seperti sekarang.` };
  }
  const anyOn = room.devices.some((d) => d.state === "on");
  const ids = new Set(room.devices.map((d) => d.id));
  const mine = cmds.filter((c) => ids.has(c.device_id));
  const loc = mine.find((c) => c.source === "local" && c.action === "turn_on" && c.status === "sent" && c.executed_at);
  if (loc) {
    const end = toDate(loc.executed_at).getTime() + LOCK_S * 1000;
    if (Date.now() < end) return { tone: "warn", title: "Dikendalikan langsung di ruangan", text: `Tombol fisik ditekan pukul ${clock(loc.executed_at)}. Pemadaman otomatis ditahan sampai ${clock(new Date(end))}.` };
  }
  if (n > 0) return anyOn
    ? { tone: "ok", title: "Ruang sedang dipakai", text: `${n} orang terdeteksi. Lampu dan AC dibiarkan menyala.` }
      : { tone: "warn", title: "Ruang terisi, perangkat mati", text: `${n} orang terdeteksi tetapi perangkat mati. Periksa kondisi ruang dan nyalakan manual bila diperlukan.` };
  if (scheduled) return { tone: "warn", title: "Terjadwal tapi kosong", text: `Menurut jadwal ruang, ${scheduled.title} berlangsung sampai ${scheduled.end_time}. Periksa kondisi ruang sebelum mengambil tindakan.` };
  const e = emptyInfo(occBy[room.room.id]);
  const dur = e && e.empty ? (e.truncated ? "lebih dari " : "") + ago(Date.now() - toDate(e.since)) : "baru saja";
  if (anyOn) return e && e.count >= EMPTY_N
    ? { tone: "bad", title: "Ruang kosong, perangkat belum mati", text: `Sudah ${e.count} pembacaan kosong berturut-turut tetapi perangkat masih menyala. Periksa riwayat perintah di bawah.` }
    : { tone: "warn", title: "Ruang kosong, perangkat masih menyala", text: `Kosong ${dur} (${e ? e.count : 1} dari ${EMPTY_N} pembacaan kosong). Perangkat dimatikan otomatis setelah ${EMPTY_N} pembacaan kosong berturut-turut.` };
  const off = mine.find((c) => c.source === "rule" && c.action === "turn_off" && c.status === "sent");
  return { tone: "ok", title: "Ruang kosong, perangkat sudah mati", text: `Kosong ${dur}.` + (off ? ` Perangkat dimatikan otomatis pukul ${clock(off.executed_at || off.created_at)}.` : "") };
}

const STATUS_LABEL = { sent: "terkirim", failed: "gagal", dry_run: "simulasi", pending: "menunggu" };
const ACTION_LABEL = { turn_on: "Dinyalakan", turn_off: "Dimatikan" };
const SOURCE_LABEL = { rule: "Otomatis", local: "Tombol fisik", manual: "Dashboard", dashboard: "Dashboard", simulator: "Simulasi" };
const roomKwh = (id) => energy ? energy.devices.filter((d) => d.room_id === id).reduce((s, d) => s + d.energy_kwh, 0) : null;
function needsAttention(room) {
  const anyOn = room.devices.some((d) => d.state === "on");
  const fresh = room.latest_person_count !== null && !isStale(room);
  return (fresh && room.latest_person_count === 0 && anyOn) || (fresh && room.latest_person_count > 0 && room.devices.length > 0 && !anyOn);
}
function roomPriority(room) {
  const fresh = room.latest_person_count !== null && !isStale(room);
  const anyOn = room.devices.some((d) => d.state === "on");
  if (fresh && room.latest_person_count === 0 && anyOn) return 0;
  if (fresh && room.latest_person_count > 0 && room.devices.length > 0 && !anyOn) return 1;
  if (room.latest_person_count === null || isStale(room)) return 3;
  return 2;
}
function emptyFor(room) {
  const e = emptyInfo(occBy[room.room.id]);
  if (isStale(room) || room.latest_person_count !== 0 || !e || !e.empty) return "";
  return (e.truncated ? "lebih dari " : "") + ago(Date.now() - toDate(e.since));
}
function renderHome(ov) {
  const attention = ov.rooms.filter(needsAttention).length;
  $("s-attention").textContent = attention;
  $("s-on").textContent = ov.total_devices_on;
  $("s-w").textContent = fmt(ov.total_power_watt_now, 0) + " W";
  $("s-kwh").textContent = energy ? fmt(energy.total_energy_kwh, 2) : "–";
  const rooms = [...ov.rooms].sort((a, b) => roomPriority(a) - roomPriority(b) || a.room.name.localeCompare(b.room.name, "id"));
  syncHomeCalendarRooms(ov.rooms);
  $("rooms").innerHTML = rooms.map((r) => {
    const n = r.latest_person_count, stale = isStale(r), attention = needsAttention(r);
    const scheduled = scheduleNow(r.room.id);
    const pill = n === null ? `<span class="pill">Belum ada data</span>`
      : stale ? `<span class="pill warn">Tidak diketahui</span>`
      : n > 0 ? `<span class="pill ok">Terisi</span>` : `<span class="pill">Kosong</span>`;
    const devs = r.devices.map((d) => {
      const state = d.state === "on" ? "menyala" : d.state === "off" ? "mati" : "status tidak diketahui";
      return `<span><span class="dot ${d.state === "on" ? "on" : ""}"></span>${esc(devLabel(d))} ${state}</span>`;
    }).join("");
    const a = advise(r), k = roomKwh(r.room.id), dur = emptyFor(r);
    return `<a class="room-card ${attention ? "attention" : stale ? "stale" : ""}" href="#/ruang/${r.room.id}">
      <div class="room-head"><strong>${esc(r.room.name)}</strong><span class="room-pills">${pill}${scheduled ? `<span class="pill scheduled">Terjadwal</span>` : ""}</span></div>
      <div class="big">${n === null || stale ? "–" : n}<span class="people"> orang</span></div>
      ${dur ? `<div class="people">Kosong ${esc(dur)}</div>` : ""}
      <div class="devline">${devs}</div>
      <div class="room-power"><span>Daya saat ini</span><strong>${fmt(r.power_watt_now, 0)} W</strong><span>Energi hari ini</span><strong>${k === null ? "–" : fmt(k, 2) + " kWh"}</strong></div>
      <div class="rec ${a.tone}">${esc(a.title)}</div>
      <div class="more">Lihat detail <span aria-hidden="true">→</span></div>
    </a>`;
  }).join("") || `<p class="people">Belum ada ruang.</p>`;
}
function spark(list) {
  const pts = list.slice(0, 60).reverse();
  if (pts.length < 2) return `<p class="people">Belum cukup data untuk grafik.</p>`;
  const W = 320, H = 80, max = Math.max(1, ...pts.map((p) => p.person_count)), step = W / (pts.length - 1);
  const xy = pts.map((p, i) => `${(i * step).toFixed(1)},${(H - 4 - (p.person_count / max) * (H - 12)).toFixed(1)}`).join(" ");
  return `<svg class="spark" viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="Riwayat jumlah orang"><polyline points="${xy}" fill="none" style="stroke:var(--accent)" stroke-width="2" vector-effect="non-scaling-stroke"/></svg><div class="row small"><span>${clock(pts[0].detected_at)}</span><span>maks ${max} orang · ${pts.length} pembacaan</span><span>${clock(pts[pts.length - 1].detected_at)}</span></div>`;
}
function safeCameraUrl(value) {
  try { const url = new URL(value); return ["http:", "https:"].includes(url.protocol) && !!url.hostname && !url.username && !url.password ? url.href : null; }
  catch (_) { return null; }
}
function mountHls(video, url, status) {
  const HlsPlayer = window.Hls;
  if (HlsPlayer && HlsPlayer.isSupported()) {
    const player = new HlsPlayer();
    player.loadSource(url); player.attachMedia(video);
    player.on(HlsPlayer.Events.MANIFEST_PARSED, () => { status.textContent = "Feed siap diputar."; video.play().catch(() => {}); });
    player.on(HlsPlayer.Events.ERROR, (_event, data) => {
      if (data.fatal) status.textContent = "Feed tidak dapat dimuat. Periksa URL, jaringan kamera, dan izin CORS sumber HLS.";
    });
    video.addEventListener("playing", () => { status.textContent = "Feed sedang diputar."; }, { once: true });
    return;
  }
  if (video.canPlayType("application/vnd.apple.mpegurl")) {
    video.src = url;
    video.addEventListener("loadedmetadata", () => { status.textContent = "Feed siap diputar."; }, { once: true });
    video.addEventListener("error", () => { status.textContent = "Browser tidak dapat memuat feed ini."; }, { once: true });
    return;
  }
  status.textContent = "Pemutar HLS tidak tersedia di browser ini.";
}
function renderCameraPreview(room) {
  const box = $("r-preview"), info = cameraPreviewRoomId === room.room.id ? cameraPreview : null;
  if (!info && cameraPreviewStatus === "loading") return;
  if (!info && cameraPreviewStatus === "error") {
    box.dataset.source = "error";
    box.innerHTML = `<div class="camera-empty">Konfigurasi feed gagal dimuat. Coba muat ulang halaman.</div>`;
    $("r-camera-note").textContent = "API preview tidak merespons.";
    return;
  }
  const cameras = Array.isArray(info?.cameras) && info.cameras.length ? info.cameras
    : info?.enabled && info.url ? [{ name: "CCTV utama", camera_id: info.camera_id, url: info.url, format: info.format }] : [];
  const source = JSON.stringify(cameras.map((c) => [c.name, c.camera_id, c.url, c.format]));
  if (box.dataset.source !== source) {
    box.dataset.source = source;
    if (!cameras.length) box.innerHTML = `<div class="camera-empty">Belum ada feed CCTV aktif untuk ruang ini. Atur kamera dari Admin.</div>`;
    else {
      box.innerHTML = cameras.map((camera, index) => {
        const label = camera.name || camera.camera_id || "CCTV", url = safeCameraUrl(camera.url);
        if (!url) return `<article class="camera-card"><div class="camera-card-head"><strong>${esc(label)}</strong><span class="tag">URL tidak valid</span></div><div class="camera-frame camera-empty">URL kamera harus memakai http atau https.</div></article>`;
        const player = camera.format === "hls"
          ? `<video data-hls-index="${index}" controls autoplay muted playsinline aria-label="Preview ${esc(label)}"></video>`
          : `<iframe data-frame-index="${index}" src="${esc(url)}" title="Preview ${esc(label)}" allow="autoplay; fullscreen; picture-in-picture" allowfullscreen loading="lazy" referrerpolicy="no-referrer"></iframe>`;
        return `<article class="camera-card"><div class="camera-card-head"><strong>${esc(label)}</strong><span class="tag">ID CCTV: ${esc(camera.camera_id || "–")}</span></div><div class="camera-frame">${player}</div><p class="camera-status" data-camera-status="${index}" role="status" aria-live="polite">Memuat feed…</p><a class="camera-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Buka sumber CCTV ↗</a></article>`;
      }).join("");
      cameras.forEach((camera, index) => {
        const url = safeCameraUrl(camera.url), status = box.querySelector(`[data-camera-status="${index}"]`);
        if (!url || !status) return;
        const video = box.querySelector(`[data-hls-index="${index}"]`);
        if (video) mountHls(video, url, status);
        const frame = box.querySelector(`[data-frame-index="${index}"]`);
        if (frame) {
          const timer = setTimeout(() => { if (status.textContent === "Memuat feed…") status.textContent = "Jika pemutar tetap kosong, periksa akses jaringan dan kebijakan embed kamera."; }, 10000);
          frame.addEventListener("load", () => { clearTimeout(timer); status.textContent = "Halaman pemutar berhasil dimuat."; }, { once: true });
        }
      });
    }
  }
  $("r-camera-note").textContent = cameras.length
    ? `${cameras.length} feed CCTV aktif untuk ${room.room.name}. Setiap kamera bisa dibuka langsung dari tautan sumber.`
    : "Tambahkan satu atau beberapa kamera dan URL pemutarnya dari Admin.";
}
function localDate(value) {
  const [year, month, day] = String(value).split("-").map(Number);
  return new Date(year, month - 1, day, 12, 0, 0);
}
function dateIso(date) {
  return `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, "0")}-${String(date.getDate()).padStart(2, "0")}`;
}
function shiftDate(date, amount) {
  const result = new Date(date);
  result.setDate(result.getDate() + amount);
  return result;
}
function weekdayIndex(date) { return (date.getDay() + 6) % 7; }
function displayDay(date, options = { weekday: "short", day: "numeric", month: "short" }) {
  return date.toLocaleDateString("id-ID", options);
}
function roomSchedules(roomId) {
  return schedules.filter((item) => item.active && item.room_id === Number(roomId))
    .sort((a, b) => a.day_of_week - b.day_of_week || a.start_time.localeCompare(b.start_time));
}
function renderScheduleInfo(roomId) {
  const now = new Date(), day = weekdayIndex(now), minute = now.getHours() * 60 + now.getMinutes();
  const items = roomSchedules(roomId);
  const current = items.find((item) => item.day_of_week === day
    && minute >= timeMinutes(item.start_time) && minute < timeMinutes(item.end_time));
  $("r-schedule-now").textContent = current
    ? `Sekarang: ${current.title} sampai ${current.end_time}`
    : "Tidak ada kelas sekarang";
  let next = null;
  for (let offset = 0; offset < 7 && !next; offset++) {
    const targetDay = (day + offset) % 7;
    next = items.find((item) => item.day_of_week === targetDay
      && (offset > 0 || timeMinutes(item.start_time) > minute));
  }
  $("r-schedule-next").textContent = next
    ? `Berikutnya: ${next.title} ${WEEKDAYS[next.day_of_week]} ${next.start_time}`
    : "Tidak ada jadwal berikutnya.";
}
function renderWeekSchedule(room) {
  renderScheduleInfo(room.room.id);
  const now = new Date();
  const monday = new Date(now.getFullYear(), now.getMonth(), now.getDate() - weekdayIndex(now) + scheduleWeekOffset * 7, 12);
  const sunday = shiftDate(monday, 6);
  $("r-schedule-week-label").textContent = `${displayDay(monday, { day: "numeric", month: "short" })} – ${displayDay(sunday, { day: "numeric", month: "short", year: "numeric" })}`;
  const items = roomSchedules(room.room.id);
  const dayDates = Array.from({ length: 7 }, (_, index) => shiftDate(monday, index));
  const dayMarkup = dayDates.map((date) => {
    const day = weekdayIndex(date), isToday = dateIso(date) === dateIso(now);
    const sessions = items.filter((item) => item.day_of_week === day);
    const events = sessions.map((item) => {
      const start = Math.max(7 * 60, timeMinutes(item.start_time));
      const end = Math.min(19 * 60, timeMinutes(item.end_time));
      if (end <= start) return "";
      const top = ((start - 7 * 60) / (12 * 60)) * 100;
      const height = ((end - start) / (12 * 60)) * 100;
      return `<div class="schedule-event" style="top:${top}%;height:${height}%" title="${esc(item.title)} · ${esc(item.start_time)}–${esc(item.end_time)}"><strong>${esc(item.title)}</strong><small>${esc(item.start_time)}–${esc(item.end_time)}</small></div>`;
    }).join("");
    const currentMinute = now.getHours() * 60 + now.getMinutes();
    const marker = isToday && currentMinute >= 420 && currentMinute <= 1140
      ? `<span class="schedule-now-marker" style="top:${((currentMinute - 420) / 720) * 100}%" aria-label="Waktu sekarang"></span>` : "";
    return `<div class="schedule-day-column ${isToday ? "is-today" : ""}"><div class="schedule-day-title">${WEEKDAYS[day]} <small>${date.getDate()}</small></div><div class="schedule-lane">${events}${marker}</div></div>`;
  });
  const axis = Array.from({ length: 13 }, (_, hour) => `<span style="top:${(hour / 12) * 100}%">${String(hour + 7).padStart(2, "0")}:00</span>`).join("");
  $("r-week-schedule").innerHTML = `<div class="week-grid-scroll"><div class="week-schedule-grid"><div class="week-axis">${axis}</div>${dayMarkup.join("")}</div></div><div class="week-agenda-mobile">${dayDates.map((date) => {
    const day = weekdayIndex(date), sessions = items.filter((item) => item.day_of_week === day);
    return `<article class="schedule-agenda-day ${dateIso(date) === dateIso(now) ? "is-today" : ""}"><h3>${WEEKDAYS[day]} · ${displayDay(date, { day: "numeric", month: "short" })}</h3>${sessions.length ? sessions.map((item) => `<p><strong>${esc(item.start_time)}–${esc(item.end_time)}</strong> · ${esc(item.title)}</p>`).join("") : `<p class="people">Tidak ada kelas terjadwal.</p>`}</article>`;
  }).join("")}</div>`;
}
function metricLabel(metric) {
  return metric === "energy" ? "Energi" : metric === "scheduled" ? "Jam terjadwal" : "Jam terisi";
}
function dayTooltip(day) {
  const date = localDate(day.date);
  return `${displayDay(date, { weekday: "long", day: "numeric", month: "short", year: "numeric" })} · ${fmt(day.occupied_hours, 1)} jam terisi · ${fmt(day.energy_kwh, 1)} kWh · ${day.classes} kelas`;
}
function renderHeatmap(container, data, opts = {}) {
  if (!data?.days?.length) {
    container.innerHTML = `<p class="people">${opts.loading === false ? "Belum ada data kalender." : "Memuat pola penggunaan…"}</p>`;
    return;
  }
  const start = localDate(data.from), end = localDate(data.to);
  const gridStart = shiftDate(start, -weekdayIndex(start));
  const weekCount = Math.floor((end - gridStart) / 86400000 / 7) + 1;
  const byDate = new Map(data.days.map((day) => [day.date, day]));
  const todayIso = dateIso(new Date());
  const selected = opts.selectedDate || data.to;
  let previousMonth = "";
  const monthLabels = [];
  const cells = [];
  for (let week = 0; week < weekCount; week++) {
    const weekDate = shiftDate(gridStart, week * 7);
    const monthKey = `${weekDate.getFullYear()}-${weekDate.getMonth()}`;
    if (monthKey !== previousMonth) {
      monthLabels.push(`<span style="grid-column:${week + 1}">${esc(weekDate.toLocaleDateString("id-ID", { month: "short" }))}</span>`);
      previousMonth = monthKey;
    }
    for (let weekday = 0; weekday < 7; weekday++) {
      const date = shiftDate(weekDate, weekday), iso = dateIso(date), day = byDate.get(iso);
      if (iso > todayIso || !day) {
        cells.push(`<span class="heat-day heat-empty" aria-hidden="true"></span>`);
        continue;
      }
      const tooltip = dayTooltip(day);
      cells.push(`<button type="button" class="heat-day heat-${day.level}${iso === todayIso ? " is-today" : ""}${iso === selected ? " is-selected" : ""}" data-usage-date="${esc(iso)}" title="${esc(tooltip)}" aria-label="${esc(tooltip)}" aria-pressed="${iso === selected}"></button>`);
    }
  }
  container.innerHTML = `<div class="heatmap-scroll" tabindex="0" aria-label="Kalender harian, gulir untuk melihat minggu terbaru"><div class="heatmap-frame"><div class="heatmap-month-row"><span></span><div class="heatmap-months" style="grid-template-columns:repeat(${weekCount},12px)">${monthLabels.join("")}</div></div><div class="heatmap-body"><div class="heatmap-weekdays"><span>Sen</span><span></span><span>Rab</span><span></span><span>Jum</span><span></span><span></span></div><div class="heatmap-grid" style="grid-template-columns:repeat(${weekCount},12px)">${cells.join("")}</div></div></div></div><div class="heatmap-legend"><span>Sedikit</span><span class="heat-day heat-0" aria-hidden="true"></span><span class="heat-day heat-1" aria-hidden="true"></span><span class="heat-day heat-2" aria-hidden="true"></span><span class="heat-day heat-3" aria-hidden="true"></span><span class="heat-day heat-4" aria-hidden="true"></span><span>Banyak</span></div>`;
  requestAnimationFrame(() => {
    const scroller = container.querySelector(".heatmap-scroll");
    if (scroller) scroller.scrollLeft = scroller.scrollWidth;
  });
}
function renderUsageDetail(screen) {
  const state = usageViews[screen];
  const root = $(({ home: "home-usage-detail", room: "room-usage-detail", summary: "summary-usage-detail" })[screen]);
  if (!state?.data) { root.innerHTML = ""; return; }
  const day = state.data.days.find((item) => item.date === state.selectedDate);
  if (!day) { root.innerHTML = ""; return; }
  const wantedRoom = screen === "room" ? Number(state.roomId) : screen === "home" && state.roomId ? Number(state.roomId) : null;
  const sessions = schedules.filter((item) => item.active && item.day_of_week === weekdayIndex(localDate(day.date))
    && (wantedRoom === null || item.room_id === wantedRoom))
    .sort((a, b) => a.start_time.localeCompare(b.start_time));
  const roomNames = Object.fromEntries((overview?.rooms || []).map((item) => [item.room.id, item.room.name]));
  const title = displayDay(localDate(day.date), { weekday: "long", day: "numeric", month: "long", year: "numeric" });
  root.innerHTML = `<h3>${esc(title)}</h3><div class="usage-detail-stats"><span>${fmt(day.occupied_hours, 1)} jam terisi</span><span>${fmt(day.energy_kwh, 2)} kWh</span><span>${fmt(day.scheduled_hours, 1)} jam terjadwal</span></div><h4>Jadwal kelas</h4>${sessions.length ? `<ul>${sessions.map((item) => `<li>${esc(item.start_time)}–${esc(item.end_time)} · ${wantedRoom === null ? `${esc(roomNames[item.room_id] || `Ruang ${item.room_id}`)} · ` : ""}${esc(item.title)}</li>`).join("")}</ul>` : `<p class="people">Tidak ada kelas terjadwal pada hari ini.</p>`}`;
}
function renderUsageCalendar(screen) {
  const state = usageViews[screen];
  const root = $(({ home: "home-usage-heatmap", room: "room-usage-heatmap", summary: "summary-usage-heatmap" })[screen]);
  const note = $(({ home: "home-usage-note", room: "room-usage-note", summary: "summary-usage-note" })[screen]);
  if (!state.data) return;
  renderHeatmap(root, state.data, { selectedDate: state.selectedDate });
  const hasDummy = state.data.days.some((day) => day.source === "dummy" || day.source === "mixed");
  note.hidden = !hasDummy;
  note.textContent = hasDummy ? "Riwayat sebelum sistem berjalan adalah data contoh." : "";
  document.querySelectorAll(`[data-calendar-controls="${screen}"] [data-metric]`).forEach((button) => {
    button.setAttribute("aria-pressed", String(button.dataset.metric === state.metric));
  });
  renderUsageDetail(screen);
}
function syncHomeCalendarRooms(rooms) {
  const select = $("home-calendar-room");
  if (!select) return;
  const selected = String(usageViews.home.roomId || "");
  select.innerHTML = `<option value="">Semua ruang</option>${rooms.map((item) => `<option value="${item.room.id}">${esc(item.room.name)}</option>`).join("")}`;
  select.value = rooms.some((item) => String(item.room.id) === selected) ? selected : "";
  usageViews.home.roomId = select.value;
}
export async function loadSchedules(force = false) {
  if (schedulesRequest) return schedulesRequest;
  if (!force && Date.now() - schedulesLoadedAt < 60000) return schedules;
  const requestId = ++schedulesRequestId;
  schedulesRequest = (async () => {
    try {
      const rows = await api("/schedules");
      if (requestId !== schedulesRequestId) return schedules;
      schedules = Array.isArray(rows) ? rows : [];
      appStore.setState({ schedules });
      schedulesError = "";
      schedulesLoadedAt = Date.now();
      if (view.name === "home" && overview) renderHome(overview);
      if (view.name === "room" && overview) {
        const room = overview.rooms.find((item) => item.room.id === view.id);
        if (room) renderRoom();
      }
      if (usageViews.home.data) renderUsageDetail("home");
      if (usageViews.room.data) renderUsageDetail("room");
      if (usageViews.summary.data) renderUsageDetail("summary");
      return schedules;
    } catch (error) {
      if (!isAbortError(error)) {
        schedulesError = error.message;
        if (view.name === "room") $("r-schedule-now").textContent = "Jadwal tidak dapat dimuat.";
      }
      return schedules;
    } finally { if (schedulesRequestId === requestId) schedulesRequest = null; }
  })();
  return schedulesRequest;
}
export async function loadUsageCalendar(screen, force = false) {
  const state = usageViews[screen];
  if (screen === "room") state.roomId = view.id;
  if (screen === "home" && !overview) {
    await new Promise((resolve) => setTimeout(resolve, 150));
    if (!overview) return null;
  }
  const key = `${state.metric}:${state.roomId || "all"}`;
  if (usageRequests[screen] && state.pendingKey === key) return usageRequests[screen];
  if (!force && state.key === key && Date.now() - (state.loadedAt || 0) < 300000) return state.data;
  if (state.key !== key) { state.data = null; state.selectedDate = ""; }
  const requestId = (state.requestId || 0) + 1;
  state.requestId = requestId;
  state.pendingKey = key;
  const params = new URLSearchParams({ weeks: "26", metric: state.metric });
  if (state.roomId) params.set("room_id", state.roomId);
  const root = $(({ home: "home-usage-heatmap", room: "room-usage-heatmap", summary: "summary-usage-heatmap" })[screen]);
  if (root) root.innerHTML = `<p class="people">Memuat pola penggunaan…</p>`;
  usageRequests[screen] = (async () => {
    try {
      const data = await api(`/dashboard/usage-calendar?${params.toString()}`);
      if (state.requestId !== requestId) return null;
      state.data = data;
      appStore.setState({ usageCalendars: { ...appStore.getState().usageCalendars, [screen]: data } });
      state.key = key;
      state.loadedAt = Date.now();
      if (!state.selectedDate || !data.days.some((day) => day.date === state.selectedDate)) state.selectedDate = data.to;
      if (view.name === screen) renderUsageCalendar(screen);
      return data;
    } catch (error) {
      if (!isAbortError(error) && state.requestId === requestId && root) root.innerHTML = `<p class="people">Gagal memuat kalender: ${esc(error.message)}</p>`;
      return null;
    } finally { if (state.requestId === requestId) usageRequests[screen] = null; }
  })();
  return usageRequests[screen];
}
function renderRoom() {
  if (!overview) { $("r-name").textContent = "Memuat…"; return; }
  const room = overview.rooms.find((r) => r.room.id === view.id);
  if (!room) { $("r-name").textContent = "Ruang tidak ditemukan"; $("r-sub").textContent = ""; return; }
  $("r-name").textContent = room.room.name;
  $("r-sub").textContent = [room.room.building, room.room.floor ? `lantai ${room.room.floor}` : null, `kapasitas ${room.room.capacity ?? "–"}`].filter(Boolean).join(" · ");
  renderCameraPreview(room);
  renderWeekSchedule(room);
  if (usageViews.room.data) renderUsageCalendar("room");
  const a = advise(room);
  $("r-rec").className = "card callout " + a.tone;
  $("r-rec").innerHTML = `<h3 class="${a.tone}">${esc(a.title)}</h3><p>${esc(a.text)}</p><p class="rule">Aturan sistem: perangkat mati otomatis setelah ${EMPTY_N} pembacaan kosong berturut-turut. Tombol fisik menahan pemadaman otomatis ${LOCK_S / 60} menit.</p>`;
  $("r-count").textContent = room.latest_person_count === null || isStale(room) ? "–" : room.latest_person_count;
  const dur = emptyFor(room);
  $("r-last").textContent = room.last_detected_at ? `Terakhir dibaca ${clock(room.last_detected_at)}${isStale(room) ? ` · ${ago(Date.now() - toDate(room.last_detected_at))} lalu` : ""}${dur ? ` · kosong ${dur}` : ""}` : "Belum ada data";
  const occ = occBy[room.room.id];
  if (occ) $("r-spark").innerHTML = spark(occ);
  const k = roomKwh(room.room.id); $("r-kwh").textContent = k === null ? "–" : fmt(k, 3) + " kWh";
  const canControl = !!adminToken();
  $("r-devs").innerHTML = room.devices.map((d) => {
    const on = d.state === "on", known = on || d.state === "off";
    const units = d.type === "light" ? `${d.lamp_count ?? "–"} lampu × ${d.watt_per_lamp == null ? "–" : fmt(d.watt_per_lamp, 1)} W` : d.unit_count != null ? `${d.unit_count} unit × ${fmt(d.watt_per_unit, 1)} W` : "daya total";
    const switchLabel = d.switch_code ? `Switch ${esc(d.switch_code)}` : `Device ${d.id}`;
    return `<div class="dev"><span><span class="dot ${on ? "on" : ""}"></span>${esc(d.name)} <small class="people">${switchLabel} · ${units} = ${fmt(d.power_watt, 1)} W total · ${known ? (on ? "menyala" : "mati") : "status tidak diketahui"}</small></span><button data-dev="${d.id}" data-act="${on ? "turn_off" : "turn_on"}" ${!canControl || !known ? "disabled" : ""} title="${!canControl ? "Masuk melalui Admin untuk mengendalikan perangkat" : !known ? "Status perangkat belum diketahui" : ""}">${on ? "Matikan" : "Nyalakan"}</button></div>`;
  }).join("") || `<p class="people">Belum ada perangkat.</p>`;
  $("r-control-hint").hidden = canControl;
  const ids = new Set(room.devices.map((d) => d.id)), names = Object.fromEntries(room.devices.map((d) => [d.id, d.name]));
  const rows = cmds.filter((c) => ids.has(c.device_id)).slice(0, 15);
  $("r-cmds").innerHTML = rows.map((c) => `<tr><td>${esc(stamp(c.created_at))}</td><td>${esc(names[c.device_id] || c.device_id)}</td><td>${esc(ACTION_LABEL[c.action] || c.action)}</td><td><span class="tag">${esc(SOURCE_LABEL[c.source] || c.source)}</span></td><td class="st-${esc(c.status)}">${esc(STATUS_LABEL[c.status] || c.status)}</td><td>${esc(c.reason || "")}</td></tr>`).join("") || `<tr><td colspan="6">Belum ada perintah untuk ruang ini.</td></tr>`;
}
function renderAdmin() {}
function groupOccupancy(records) {
  const grouped = {};
  for (const row of records || []) (grouped[row.room_id] ||= []).push(row);
  return grouped;
}
function updateFreshness() {
  const bad = errors.length > 0 || !health;
  document.body.classList.toggle("data-stale", bad);
  const label = $("last-updated");
  if (lastUpdatedAt) label.textContent = `Diperbarui ${new Date(lastUpdatedAt).toLocaleTimeString("id-ID", { hour12: false })}${bad ? " · koneksi bermasalah, menampilkan data terakhir" : ""}`;
  else label.textContent = bad ? "Belum berhasil memuat data dari API." : "Memuat data…";
  const warn = $("err");
  if (!health) { warn.textContent = "API tidak terjangkau · data yang terlihat mungkin sudah lama"; warn.hidden = false; }
  else if (errors.length) { warn.textContent = `Sebagian data tidak terbarui (${errors.length} bagian)`; warn.hidden = false; }
  else warn.hidden = true;
}
export async function refresh() {
  if (document.hidden) return;
  if (inFlight) { refreshQueued = true; return; }
  inFlight = true; errors = [];
  const myView = { ...view };
  const previewRequest = myView.name === "room" ? safe(`/preview?room_id=${myView.id}`) : Promise.resolve(null);
  try {
    const summaryOnly = myView.name === "summary";
    const [ov, hl, en, cm, cp] = await Promise.all([
      summaryOnly && !overview ? safe("/dashboard/overview") : summaryOnly ? Promise.resolve(null) : safe("/dashboard/overview"),
      safe("/health"),
      summaryOnly ? Promise.resolve(null) : safe("/dashboard/energy?start=" + encodeURIComponent(dayStart())),
      summaryOnly ? Promise.resolve(null) : safe("/commands?limit=100"),
      previewRequest,
    ]);
    if (ov) overview = ov;
    if (en) energy = en;
    if (cm) cmds = cm;
    health = hl;
    if (myView.name === "room") {
      if (cp) { cameraPreview = cp; cameraPreviewRoomId = myView.id; cameraPreviewStatus = "ready"; }
      else cameraPreviewStatus = "error";
    }
    if (overview && (myView.name === "home" || myView.name === "room")) {
      if (myView.name === "room") {
        const rows = await safe(`/occupancy?room_id=${myView.id}&limit=${OCC_LIMIT}`);
        if (rows) occBy[myView.id] = rows;
      } else {
        const rows = await safe(`/occupancy/recent?limit_per_room=${OCC_LIMIT}`);
        if (rows) occBy = groupOccupancy(rows);
      }
    }
    if (ov && hl) lastUpdatedAt = Date.now();
    if (myView.name !== view.name || myView.id !== view.id) { refreshQueued = true; return; }
    appStore.setState({ overview, health, energy, commands: cmds, occupancyByRoom: occBy, errors: [...errors], lastUpdatedAt });
    if (view.name === "home") { if (overview) renderHome(overview); }
    else if (view.name === "room") renderRoom();
    else if (view.name === "admin") renderAdmin();
    else if (view.name === "summary" && usageViews.summary.data) renderUsageDetail("summary");
    updateFreshness();
  } finally {
    inFlight = false;
    if (refreshQueued) { refreshQueued = false; if (!document.hidden) refresh(); }
  }
}

document.addEventListener("click", async (ev) => {
  const b = ev.target.closest("button[data-dev]");
  if (!b || b.disabled) return;
  const room = overview?.rooms.find((item) => item.room.id === view.id);
  if (b.dataset.act === "turn_off" && room && !isStale(room) && room.latest_person_count > 0) {
    if (!window.confirm(`${room.room.name} masih terisi (${room.latest_person_count} orang). Tetap matikan perangkat ini?`)) return;
  }
  const label = b.textContent; b.disabled = true; b.setAttribute("aria-busy", "true"); b.textContent = "Mengirim…";
  try {
    await api("/commands", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ device_id: +b.dataset.dev, action: b.dataset.act, reason: "tombol dashboard" }) });
    $("r-msg").textContent = "Perintah dikirim.";
    await refresh();
  } catch (e) { $("r-msg").textContent = "Gagal: " + e.message; }
  finally { if (b.isConnected) { b.disabled = false; b.removeAttribute("aria-busy"); b.textContent = label; } }
});
document.addEventListener("click", (ev) => {
  const metricButton = ev.target.closest("[data-calendar-controls] [data-metric]");
  if (metricButton) {
    const screen = metricButton.closest("[data-calendar-controls]").dataset.calendarControls;
    const state = usageViews[screen];
    if (!state || state.metric === metricButton.dataset.metric) return;
    state.metric = metricButton.dataset.metric;
    state.key = "";
    loadUsageCalendar(screen, true);
    return;
  }
  const dayButton = ev.target.closest("[data-usage-date]");
  if (dayButton) {
    const screen = dayButton.closest("#home-usage-heatmap") ? "home"
      : dayButton.closest("#summary-usage-heatmap") ? "summary" : "room";
    usageViews[screen].selectedDate = dayButton.dataset.usageDate;
    renderUsageCalendar(screen);
    return;
  }
  if (ev.target.closest("#r-schedule-prev")) {
    scheduleWeekOffset -= 1;
    const room = overview?.rooms.find((item) => item.room.id === view.id);
    if (room) renderWeekSchedule(room);
  } else if (ev.target.closest("#r-schedule-next-week")) {
    scheduleWeekOffset += 1;
    const room = overview?.rooms.find((item) => item.room.id === view.id);
    if (room) renderWeekSchedule(room);
  }
});
document.addEventListener("change", (ev) => {
  if (ev.target.id === "home-calendar-room") {
    usageViews.home.roomId = ev.target.value;
    usageViews.home.key = "";
    usageViews.home.selectedDate = "";
    loadUsageCalendar("home", true);
  }
});
