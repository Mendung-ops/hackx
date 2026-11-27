import { appStore } from "./store.js";

(() => {
  const $ = (id) => document.getElementById(id);
  const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const fmt = (n) => Number(n || 0).toLocaleString("id-ID", { maximumFractionDigits: 1 });
  const root = $("admin-management");
  if (!root) return;

  root.innerHTML = `
    <section class="card">
      <h2>Akses admin</h2>
      <p class="people">Token admin diperlukan untuk mengubah kelas, perangkat, dan CCTV.</p>
      <div id="admin-login-form" class="send">
        <input class="token-input" type="password" id="admin-token" autocomplete="current-password" aria-label="Token admin" placeholder="ADMIN_TOKEN">
        <button class="primary" id="admin-login">Masuk</button>
      </div>
      <div id="admin-session" class="row" hidden><span class="tag">Admin aktif</span><button id="admin-logout">Keluar</button></div>
      <div class="msg" id="admin-auth-msg" role="status" aria-live="polite" aria-atomic="true"></div>
    </section>
    <div id="admin-panel" hidden>
      <section class="card">
        <h2>Simulasi okupansi</h2>
        <p class="people">Kirim pembacaan uji ke mesin aturan. Akses ini memerlukan token admin.</p>
        <div class="send"><label for="sim-room">Ruang</label><select id="sim-room"></select><label for="sim-count">Orang</label><input id="sim-count" type="number" min="0" step="1" value="0"><button class="primary" id="sim-send">Kirim pembacaan</button></div>
        <div class="msg" id="sim-msg" role="status" aria-live="polite" aria-atomic="true"></div>
      </section>
      <section class="card">
        <div class="row"><h2 style="margin:0">Kelas / ruangan</h2><select id="admin-room-select" aria-label="Pilih kelas"></select></div>
        <p class="people">Buat kelas baru atau pilih kelas yang ada untuk mengubah nama, gedung, dan kapasitasnya.</p>
        <div class="admin-fields">
          <label class="admin-field">Nama / kode kelas<input id="admin-room-name" maxlength="100" placeholder="contoh: Kelas Demo 01"></label>
          <label class="admin-field">Gedung<input id="admin-room-building" maxlength="100" placeholder="Gedung A"></label>
          <label class="admin-field">Lantai<input id="admin-room-floor" maxlength="20" placeholder="1"></label>
          <label class="admin-field">Kapasitas orang<input id="admin-room-capacity" type="number" min="0" step="1" placeholder="40"></label>
        </div>
        <button class="primary" id="admin-room-save">Simpan kelas</button>
        <div class="msg" id="admin-room-msg" role="status" aria-live="polite"></div>
      </section>

      <section class="card" id="admin-device-panel" hidden>
        <div class="row"><h2 style="margin:0">Lampu, AC, dan switch</h2><button id="admin-device-new">Tambah switch / perangkat</button></div>
        <p class="admin-note">Setiap entri adalah satu switch/relay dengan kontrol nyala-mati sendiri. Untuk 9 lampu yang dibagi ke 3 switch, buat 3 entri dan isi jumlah lampu di masing-masing switch. Daya total = jumlah unit × watt per unit. Energi = watt total × jam menyala ÷ 1000; 36 W selama 1 jam = 0,036 kWh.</p>
        <div id="admin-devices-list" class="admin-list"></div>
        <h3 id="admin-device-form-title">Tambah perangkat</h3>
        <div class="admin-fields">
          <label class="admin-field">Jenis perangkat<select id="admin-device-type"><option value="light">Lampu</option><option value="ac">AC</option></select></label>
          <label class="admin-field">Nama / jenis (mis. LED, TL, AC 1.5 PK)<input id="admin-device-name" maxlength="100" placeholder="Lampu LED"></label>
          <label class="admin-field">Kode switch / relay<input id="admin-device-switch" maxlength="20" placeholder="A"></label>
        </div>
        <div id="admin-light-fields" class="admin-fields">
          <label class="admin-field">Jumlah lampu pada switch<input id="admin-lamp-count" type="number" min="1" max="100" step="1"></label>
          <label class="admin-field">Watt per lampu<input id="admin-lamp-watt" type="number" min="0.1" step="0.1" placeholder="12"></label>
        </div>
        <div id="admin-ac-fields" class="admin-fields" hidden>
          <label class="admin-field">Jumlah unit AC pada switch<input id="admin-ac-count" type="number" min="1" max="100" step="1"></label>
          <label class="admin-field">Watt per unit AC<input id="admin-ac-watt" type="number" min="0.1" step="0.1" placeholder="900"></label>
        </div>
        <label class="admin-field">Catatan perangkat / modul<input id="admin-device-note" maxlength="200" placeholder="Relay panel sisi kiri"></label>
        <label id="admin-device-active-wrap" class="people" hidden><input id="admin-device-active" type="checkbox"> Perangkat aktif</label>
        <p class="people" id="admin-device-calculation">Daya total akan dihitung dari jumlah × watt per unit.</p>
        <button class="primary" id="admin-device-save">Simpan perangkat</button>
        <button id="admin-device-cancel" hidden>Batal edit</button>
        <div class="msg" id="admin-device-msg" role="status" aria-live="polite"></div>
      </section>

      <section class="card" id="admin-camera-panel" hidden>
        <div class="row"><h2 style="margin:0">CCTV / sumber vision</h2><button id="admin-camera-new">Tambah kamera</button></div>
        <p class="people">Satu kamera punya nama, ID CCTV, dan URL akses lapangan sendiri. ID CCTV harus muncul sebagai satu segmen pada jalur URL, seperti <code>kelas-demo-01</code> di http://10.124.223.85:8889/kelas-demo-01/</p>
        <div id="admin-cameras-list" class="admin-list"></div>
        <h3 id="admin-camera-form-title">Tambah kamera</h3>
        <div class="admin-fields admin-camera-fields">
          <label class="admin-field">Nama tampilan<input id="admin-camera-name" maxlength="100" placeholder="mis. CCTV A101 depan"></label>
          <label class="admin-field">ID CCTV / stream<input id="admin-camera-id" maxlength="100" placeholder="mis. kelas-demo-01"><small>Harus sama dengan nama path di URL.</small></label>
          <label class="admin-field admin-camera-url-field">URL akses kamera<input id="admin-camera-url" type="url" maxlength="500" placeholder="http://&lt;IP-laptop-vision&gt;:8889/kelas-demo-01/"><small>Gunakan http/https dan jangan masukkan username/password ke URL.</small></label>
        </div>
        <fieldset class="admin-camera-auth">
          <legend>Login CCTV <span>(opsional · HTTP Basic)</span></legend>
          <div class="admin-camera-auth-fields">
            <label class="admin-field">Username<input id="admin-camera-auth-user" autocomplete="username" maxlength="100" placeholder="Username CCTV"></label>
            <label class="admin-field">Password<input id="admin-camera-auth-pass" type="password" autocomplete="new-password" placeholder="Password CCTV"></label>
          </div>
          <p class="people">Kredensial hanya disimpan sementara di memori server dev, tidak masuk database, dan hilang saat server dimulai ulang.</p>
        </fieldset>
        <label id="admin-camera-active-wrap" class="people" hidden><input id="admin-camera-active" type="checkbox"> Kamera aktif di preview</label>
        <button class="primary" id="admin-camera-save">Simpan kamera</button>
        <button id="admin-camera-clear-auth" hidden>Hapus login tersimpan</button>
        <button id="admin-camera-cancel" hidden>Batal edit</button>
        <div class="msg" id="admin-camera-msg" role="status" aria-live="polite"></div>
      </section>
      <section class="card" id="admin-schedule-panel" hidden>
        <div class="row"><h2 style="margin:0">Jadwal kelas</h2><button id="admin-schedule-new">Tambah jadwal</button></div>
        <p class="people">Jadwal berulang mingguan hanya menjadi informasi dan rekomendasi di dashboard.</p>
        <div id="admin-schedules-list" class="admin-list"></div>
        <h3 id="admin-schedule-form-title">Tambah jadwal</h3>
        <div class="admin-fields">
          <label class="admin-field">Hari<select id="admin-schedule-day"><option value="0">Senin</option><option value="1">Selasa</option><option value="2">Rabu</option><option value="3">Kamis</option><option value="4">Jumat</option><option value="5">Sabtu</option><option value="6">Minggu</option></select></label>
          <label class="admin-field">Jam mulai<input id="admin-schedule-start" type="time" required></label>
          <label class="admin-field">Jam selesai<input id="admin-schedule-end" type="time" required></label>
          <label class="admin-field">Mata kuliah / kegiatan<input id="admin-schedule-title" maxlength="100" placeholder="Pemrograman Web"></label>
        </div>
        <label class="people"><input id="admin-schedule-active" type="checkbox" checked> Jadwal aktif</label>
        <div class="send"><button class="primary" id="admin-schedule-save">Simpan jadwal</button><button id="admin-schedule-cancel" hidden>Batal edit</button></div>
        <div class="msg" id="admin-schedule-msg" role="status" aria-live="polite"></div>
        <div class="admin-seed-actions"><button id="admin-schedule-seed">Isi jadwal contoh</button><button id="admin-usage-seed">Isi riwayat contoh</button></div>
        <p class="people">Jadwal contoh tidak mengganti jadwal yang sudah ada. Riwayat contoh hanya mengisi tanggal yang belum memiliki data.</p>
      </section>
    </div>`;

  let token = sessionStorage.getItem("hackx.adminToken") || "";
  let rooms = [], devices = [], cameras = [], schedules = [];
  let currentRoomId = null, editingDeviceId = null, editingCameraId = null, editingScheduleId = null;
  let loading = false;

  async function request(path, options = {}) {
    const headers = { ...(options.headers || {}) };
    if (token) headers["X-Admin-Token"] = token;
    const response = await fetch(path, { ...options, headers });
    let data = null;
    try { data = await response.json(); } catch (_) {}
    if (!response.ok) {
      const detail = data && data.detail;
      const error = new Error(typeof detail === "string" ? detail : `${path} → ${response.status}`);
      error.status = response.status;
      error.detail = detail;
      throw error;
    }
    return data;
  }

  function authMessage(text) { $("admin-auth-msg").textContent = text; }
  function roomMessage(text) { $("admin-room-msg").textContent = text; }
  function deviceMessage(text) { $("admin-device-msg").textContent = text; }
  function cameraMessage(text) { $("admin-camera-msg").textContent = text; }
  function scheduleMessage(text) { $("admin-schedule-msg").textContent = text; }
  function notifyDataChanged() { window.dispatchEvent(new Event("hackx:data-changed")); }

  function showSignedIn(signedIn) {
    $("admin-login-form").hidden = signedIn;
    $("admin-session").hidden = !signedIn;
    $("admin-panel").hidden = !signedIn;
  }

  function fillRoom(room) {
    currentRoomId = room?.id ?? null;
    $("admin-room-name").value = room?.name || "";
    $("admin-room-building").value = room?.building || "";
    $("admin-room-floor").value = room?.floor || "";
    $("admin-room-capacity").value = room?.capacity ?? "";
    $("admin-room-save").textContent = room ? "Simpan perubahan kelas" : "Tambah kelas";
    const canManage = !!room;
    $("admin-device-panel").hidden = !canManage;
    $("admin-camera-panel").hidden = !canManage;
    $("admin-schedule-panel").hidden = !canManage;
    if (!room) {
      devices = []; cameras = []; schedules = [];
      renderDevices(); renderCameras(); renderSchedules();
      resetDeviceForm(); resetCameraForm(); resetScheduleForm();
    }
  }

  function renderRooms(selectedId = currentRoomId) {
    const simSelect = $("sim-room");
    simSelect.innerHTML = rooms.map((room) => `<option value="${room.id}">${esc(room.name)}</option>`).join("");
    if (currentRoomId && rooms.some((room) => room.id === Number(currentRoomId))) simSelect.value = String(currentRoomId);
    const select = $("admin-room-select");
    select.innerHTML = `<option value="new">+ Tambah kelas</option>` + rooms.map((room) => {
      const where = [room.building, room.floor ? `Lt ${room.floor}` : ""].filter(Boolean).join(" · ");
      return `<option value="${room.id}">${esc(room.name)}${where ? ` — ${esc(where)}` : ""}</option>`;
    }).join("");
    const chosen = selectedId && rooms.some((room) => room.id === Number(selectedId))
      ? String(selectedId) : rooms.length ? String(rooms[0].id) : "new";
    select.value = chosen;
    const room = rooms.find((item) => String(item.id) === chosen) || null;
    fillRoom(room);
    return room;
  }

  async function loadRoomResources(roomId) {
    if (!roomId) return;
    const [deviceRows, cameraRows, scheduleRows] = await Promise.all([
      request(`/admin/devices?room_id=${roomId}&include_inactive=true`),
      request(`/admin/cameras?room_id=${roomId}&include_inactive=true`),
      request(`/schedules?room_id=${roomId}`),
    ]);
    if (currentRoomId !== roomId) return;
    devices = deviceRows; cameras = cameraRows; schedules = scheduleRows;
    renderDevices(); renderCameras(); renderSchedules();
    resetDeviceForm(); resetCameraForm(); resetScheduleForm();
  }

  async function loadRooms(selectedId = currentRoomId) {
    rooms = await request("/admin/rooms");
    const room = renderRooms(selectedId);
    if (room) await loadRoomResources(room.id);
  }

  async function openAdmin() {
    if (loading) return;
    if (!token) { showSignedIn(false); return; }
    loading = true;
    try {
      await request("/admin/ping");
      sessionStorage.setItem("hackx.adminToken", token);
      showSignedIn(true);
      authMessage("Token diterima.");
      await loadRooms(currentRoomId);
    } catch (error) {
      token = "";
      sessionStorage.removeItem("hackx.adminToken");
      $("admin-token").value = "";
      showSignedIn(false);
      authMessage(`Akses admin gagal: ${error.message}`);
    } finally {
      loading = false;
    }
  }

  function resetDeviceForm() {
    editingDeviceId = null;
    $("admin-device-form-title").textContent = "Tambah perangkat / switch";
    $("admin-device-save").textContent = "Tambah perangkat";
    $("admin-device-cancel").hidden = true;
    $("admin-device-type").disabled = false;
    $("admin-device-type").value = "light";
    $("admin-device-name").value = "";
    $("admin-device-switch").value = "";
    $("admin-lamp-count").value = "";
    $("admin-lamp-watt").value = "";
    $("admin-ac-count").value = "1";
    $("admin-ac-watt").value = "";
    $("admin-device-note").value = "";
    $("admin-device-active-wrap").hidden = true;
    $("admin-device-active").checked = true;
    updateDeviceTypeFields();
    deviceMessage("");
  }

  function updateDeviceTypeFields() {
    const isLight = $("admin-device-type").value === "light";
    $("admin-light-fields").hidden = !isLight;
    $("admin-ac-fields").hidden = isLight;
    const count = Number(isLight ? $("admin-lamp-count").value : $("admin-ac-count").value);
    const watts = Number(isLight ? $("admin-lamp-watt").value : $("admin-ac-watt").value);
    $("admin-device-calculation").textContent = count > 0 && watts > 0
      ? `Perkiraan daya switch ini: ${count} × ${fmt(watts)} W = ${fmt(count * watts)} W total.`
      : "Daya total dihitung dari jumlah unit × watt per unit.";
  }

  function editDevice(id) {
    const device = devices.find((item) => item.id === id);
    if (!device) return;
    editingDeviceId = device.id;
    $("admin-device-form-title").textContent = `Edit device #${device.id}`;
    $("admin-device-save").textContent = "Simpan perubahan";
    $("admin-device-cancel").hidden = false;
    $("admin-device-type").value = device.type;
    $("admin-device-type").disabled = true;
    $("admin-device-name").value = device.name;
    $("admin-device-switch").value = device.switch_code || "";
    $("admin-device-note").value = device.module_note || "";
    $("admin-device-active-wrap").hidden = false;
    $("admin-device-active").checked = !!device.active;
    if (device.type === "light") {
      $("admin-lamp-count").value = device.lamp_count ?? 1;
      $("admin-lamp-watt").value = device.watt_per_lamp ?? (device.power_watt / (device.lamp_count || 1));
    } else {
      $("admin-ac-count").value = device.unit_count ?? 1;
      $("admin-ac-watt").value = device.watt_per_unit ?? device.power_watt;
    }
    updateDeviceTypeFields();
    deviceMessage("");
    $("admin-device-name").focus();
  }

  function renderDevices() {
    const list = $("admin-devices-list");
    if (!devices.length) {
      list.innerHTML = `<p class="people">Belum ada switch atau perangkat di kelas ini.</p>`;
      return;
    }
    list.innerHTML = devices.map((device) => {
      const quantity = device.type === "light"
        ? `${device.lamp_count ?? "–"} lampu × ${device.watt_per_lamp == null ? "–" : fmt(device.watt_per_lamp)} W`
        : device.unit_count != null
          ? `${device.unit_count} unit × ${fmt(device.watt_per_unit)} W`
          : "daya total lama";
      const state = device.active ? "Aktif" : "Nonaktif";
      return `<article class="admin-item">
        <div><strong>${esc(device.name)}</strong><small>ID device ${device.id} · ${device.type === "light" ? "Lampu" : "AC"} · switch ${esc(device.switch_code || "–")} · ${quantity} = ${fmt(device.power_watt)} W total · ${state}</small>
        <details><summary class="people">Topik hardware</summary><small>Command: ${esc(device.topics.command)} · State: ${esc(device.topics.state)}${device.topics.event ? ` · Event: ${esc(device.topics.event)}` : ""}</small></details></div>
        <div class="admin-item-actions"><button data-admin-action="edit-device" data-id="${device.id}">Edit</button><button data-admin-action="toggle-device" data-id="${device.id}">${device.active ? "Nonaktifkan" : "Aktifkan"}</button></div>
      </article>`;
    }).join("");
  }

  async function saveDevice() {
    if (!currentRoomId) { deviceMessage("Simpan kelas terlebih dahulu."); return; }
    const type = $("admin-device-type").value;
    const name = $("admin-device-name").value.trim();
    const switchCode = $("admin-device-switch").value.trim();
    if (!name || !switchCode) { deviceMessage("Isi nama/jenis perangkat dan kode switch/relay."); return; }
    const body = {
      name, switch_code: switchCode || null,
      module_note: $("admin-device-note").value.trim() || null,
    };
    if (type === "light") {
      body.lamp_count = Number($("admin-lamp-count").value);
      body.watt_per_lamp = Number($("admin-lamp-watt").value);
      if (!(body.lamp_count > 0) || !(body.watt_per_lamp > 0)) {
        deviceMessage("Isi jumlah lampu dan watt per lampu dengan angka lebih dari 0."); return;
      }
    } else {
      body.unit_count = Number($("admin-ac-count").value);
      body.watt_per_unit = Number($("admin-ac-watt").value);
      if (!(body.unit_count > 0) || !(body.watt_per_unit > 0)) {
        deviceMessage("Isi jumlah AC dan watt per unit dengan angka lebih dari 0."); return;
      }
    }
    try {
      let saved;
      if (editingDeviceId) {
        body.active = $("admin-device-active").checked;
        saved = await request(`/admin/devices/${editingDeviceId}`, {
          method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
      } else {
        body.room_id = currentRoomId;
        body.type = type;
        saved = await request("/admin/devices", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
      }
      await loadRoomResources(currentRoomId);
      if (saved) editDevice(saved.id);
      deviceMessage(`Tersimpan. Daya switch ${fmt(saved.power_watt)} W; ID device ${saved.id}.`);
      notifyDataChanged();
    } catch (error) { deviceMessage(`Gagal menyimpan: ${error.message}`); }
  }

  async function toggleDevice(id) {
    const device = devices.find((item) => item.id === id);
    if (!device) return;
    try {
      await request(`/admin/devices/${id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: !device.active }),
      });
      await loadRoomResources(currentRoomId);
      notifyDataChanged();
    } catch (error) { deviceMessage(`Gagal mengubah status: ${error.message}`); }
  }

  function resetCameraForm() {
    editingCameraId = null;
    $("admin-camera-form-title").textContent = "Tambah kamera";
    $("admin-camera-save").textContent = "Tambah kamera";
    $("admin-camera-cancel").hidden = true;
    $("admin-camera-name").value = "";
    $("admin-camera-id").value = "";
    $("admin-camera-url").value = "";
    $("admin-camera-auth-user").value = "";
    $("admin-camera-auth-pass").value = "";
    $("admin-camera-active-wrap").hidden = true;
    $("admin-camera-clear-auth").hidden = true;
    $("admin-camera-active").checked = true;
    cameraMessage("");
  }

  function safeCameraUrl(value) {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) && !!url.hostname && !url.username && !url.password ? url.href : null;
    } catch (_) { return null; }
  }

  function cameraErrorMessage(error) {
    const details = error?.detail;
    const explain = (item) => {
      const field = Array.isArray(item?.loc) ? item.loc.filter((part) => part !== "body").slice(-1)[0] : null;
      const message = String(item?.msg || "");
      if (/ID CCTV harus|salah satu segmen path/i.test(message)) {
        return "ID CCTV harus sama dengan salah satu bagian path URL, contoh: URL http://<host>/kelas-demo-01/ → ID kelas-demo-01.";
      }
      if (field === "camera_url") {
        if (/kredensial/i.test(message)) return "URL akses kamera tidak boleh berisi username atau password.";
        if (/required/i.test(message)) return "URL akses kamera wajib diisi.";
        return "URL akses kamera harus berupa URL http:// atau https:// yang valid tanpa kredensial.";
      }
      if (field === "camera_id") {
        if (/required/i.test(message)) return "ID CCTV / stream wajib diisi.";
        return "ID CCTV / stream tidak valid.";
      }
      if (field === "name") {
        if (/required/i.test(message)) return "Nama tampilan wajib diisi.";
        return "Nama tampilan tidak valid.";
      }
      if (field === "room_id") return "Pilih atau simpan ruang terlebih dahulu.";
      if (field === "auth_username" || field === "auth_password") return "Isi username dan password CCTV bersamaan.";
      return "Periksa kembali nama tampilan, ID CCTV, dan URL akses kamera.";
    };
    if (Array.isArray(details)) return [...new Set(details.map(explain))].join(" ");
    if (typeof details === "string") {
      if (/ID CCTV harus|salah satu segmen path/i.test(details)) return explain({ msg: details });
      if (/kredensial/i.test(details)) return "URL akses kamera tidak boleh berisi username atau password.";
      if (/camera_url|http\(s\)/i.test(details)) return "URL akses kamera harus berupa URL http:// atau https:// yang valid tanpa kredensial.";
      return details;
    }
    return error?.message || "Kamera gagal disimpan. Periksa kembali datanya.";
  }

  function renderCameras() {
    const list = $("admin-cameras-list");
    if (!cameras.length) {
      list.innerHTML = `<p class="people">Belum ada CCTV untuk kelas ini. Tambahkan kamera A, B, C, dan seterusnya.</p>`;
      return;
    }
    list.innerHTML = cameras.map((camera) => {
      const url = safeCameraUrl(camera.camera_url);
      return `<article class="admin-item">
      <div><strong>${esc(camera.name)}</strong><small>ID CCTV ${esc(camera.camera_id)} · ${camera.active ? "Aktif di preview" : "Nonaktif"}${camera.auth_configured ? " · Login sementara tersimpan" : ""}</small>
        ${url ? `<a class="camera-link" href="${esc(url)}" target="_blank" rel="noopener noreferrer">Buka URL lapangan ↗</a>` : `<small>URL kamera tidak valid</small>`}</div>
      <div class="admin-item-actions"><button data-admin-action="edit-camera" data-id="${camera.id}">Edit</button><button data-admin-action="toggle-camera" data-id="${camera.id}">${camera.active ? "Nonaktifkan" : "Aktifkan"}</button></div>
    </article>`;
    }).join("");
  }

  function editCamera(id) {
    const camera = cameras.find((item) => item.id === id);
    if (!camera) return;
    editingCameraId = camera.id;
    $("admin-camera-form-title").textContent = `Edit CCTV #${camera.id}`;
    $("admin-camera-save").textContent = "Simpan perubahan";
    $("admin-camera-cancel").hidden = false;
    $("admin-camera-name").value = camera.name;
    $("admin-camera-id").value = camera.camera_id;
    $("admin-camera-url").value = camera.camera_url;
    $("admin-camera-auth-user").value = "";
    $("admin-camera-auth-pass").value = "";
    $("admin-camera-active-wrap").hidden = false;
    $("admin-camera-clear-auth").hidden = !camera.auth_configured;
    $("admin-camera-active").checked = !!camera.active;
    cameraMessage("");
    $("admin-camera-name").focus();
  }

  async function saveCamera() {
    if (!currentRoomId) { cameraMessage("Simpan kelas terlebih dahulu."); return; }
    const name = $("admin-camera-name").value.trim();
    const cameraId = $("admin-camera-id").value.trim();
    const cameraUrl = $("admin-camera-url").value.trim();
    const authUsername = $("admin-camera-auth-user").value.trim();
    const authPassword = $("admin-camera-auth-pass").value;
    if (!name || !cameraId || !cameraUrl) {
      cameraMessage("Nama kamera, ID CCTV, dan URL sumber wajib diisi."); return;
    }
    const safeUrl = safeCameraUrl(cameraUrl);
    if (!safeUrl) { cameraMessage("URL kamera harus berupa alamat http atau https yang valid tanpa kredensial."); return; }
    const body = { name, camera_id: cameraId, camera_url: safeUrl };
    if (Boolean(authUsername) !== Boolean(authPassword)) {
      cameraMessage("Isi username dan password CCTV bersamaan, atau kosongkan keduanya."); return;
    }
    if (authUsername && authPassword) {
      body.auth_username = authUsername;
      body.auth_password = authPassword;
    }
    try {
      if (editingCameraId) {
        body.active = $("admin-camera-active").checked;
        await request(`/admin/cameras/${editingCameraId}`, {
          method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
      } else {
        body.room_id = currentRoomId;
        await request("/admin/cameras", {
          method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body),
        });
      }
      await loadRoomResources(currentRoomId);
      cameraMessage(authUsername ? "Kamera tersimpan. Login aktif sampai server dev dimulai ulang." : "URL CCTV tersimpan untuk kelas ini.");
      notifyDataChanged();
    } catch (error) { cameraMessage(`Gagal menyimpan: ${cameraErrorMessage(error)}`); }
  }

  async function toggleCamera(id) {
    const camera = cameras.find((item) => item.id === id);
    if (!camera) return;
    try {
      await request(`/admin/cameras/${id}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ active: !camera.active }),
      });
      await loadRoomResources(currentRoomId);
      notifyDataChanged();
    } catch (error) { cameraMessage(`Gagal mengubah status: ${error.message}`); }
  }

  async function clearCameraAuth() {
    if (!editingCameraId || !confirm("Hapus username dan password CCTV dari memori server?")) return;
    try {
      await request(`/admin/cameras/${editingCameraId}`, {
        method: "PATCH", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ clear_auth: true }),
      });
      await loadRoomResources(currentRoomId);
      cameraMessage("Login CCTV dihapus dari memori server.");
      notifyDataChanged();
    } catch (error) { cameraMessage(`Gagal menghapus login: ${error.message}`); }
  }

  const weekdays = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"];
  function resetScheduleForm() {
    editingScheduleId = null;
    $("admin-schedule-form-title").textContent = "Tambah jadwal";
    $("admin-schedule-save").textContent = "Simpan jadwal";
    $("admin-schedule-cancel").hidden = true;
    $("admin-schedule-day").value = "0";
    $("admin-schedule-start").value = "08:00";
    $("admin-schedule-end").value = "09:00";
    $("admin-schedule-title").value = "";
    $("admin-schedule-active").checked = true;
    scheduleMessage("");
  }

  function renderSchedules() {
    const list = $("admin-schedules-list");
    if (!list) return;
    if (!schedules.length) {
      list.innerHTML = `<p class="people">Belum ada jadwal untuk ruang ini.</p>`;
      return;
    }
    list.innerHTML = schedules.map((item) => `<article class="admin-item">
      <div><strong>${esc(item.title)}</strong><small>${weekdays[item.day_of_week]} · ${esc(item.start_time)}–${esc(item.end_time)} · ${item.active ? "Aktif" : "Nonaktif"}</small></div>
      <div class="admin-item-actions"><button data-admin-action="edit-schedule" data-id="${item.id}">Edit</button><button data-admin-action="delete-schedule" data-id="${item.id}">Hapus</button></div>
    </article>`).join("");
  }

  function editSchedule(id) {
    const item = schedules.find((row) => row.id === id);
    if (!item) return;
    editingScheduleId = item.id;
    $("admin-schedule-form-title").textContent = `Edit jadwal #${item.id}`;
    $("admin-schedule-save").textContent = "Simpan perubahan";
    $("admin-schedule-cancel").hidden = false;
    $("admin-schedule-day").value = String(item.day_of_week);
    $("admin-schedule-start").value = item.start_time;
    $("admin-schedule-end").value = item.end_time;
    $("admin-schedule-title").value = item.title;
    $("admin-schedule-active").checked = !!item.active;
    scheduleMessage("");
    $("admin-schedule-title").focus();
  }

  async function saveSchedule() {
    if (!currentRoomId) { scheduleMessage("Simpan ruang terlebih dahulu."); return; }
    const day = Number($("admin-schedule-day").value);
    const start = $("admin-schedule-start").value;
    const end = $("admin-schedule-end").value;
    const title = $("admin-schedule-title").value.trim();
    if (!title || !start || !end) { scheduleMessage("Isi hari, jam mulai, jam selesai, dan mata kuliah."); return; }
    if (end <= start) { scheduleMessage("Jam selesai harus setelah jam mulai."); return; }
    const body = { day_of_week: day, start_time: start, end_time: end, title, active: $("admin-schedule-active").checked };
    try {
      if (editingScheduleId) {
        await request(`/admin/schedules/${editingScheduleId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      } else {
        body.room_id = currentRoomId;
        await request("/admin/schedules", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      }
      await loadRoomResources(currentRoomId);
      scheduleMessage("Jadwal tersimpan.");
      notifyDataChanged();
    } catch (error) { scheduleMessage(`Gagal menyimpan jadwal: ${error.message}`); }
  }

  async function deleteSchedule(id) {
    const item = schedules.find((row) => row.id === id);
    if (!item || !window.confirm(`Hapus jadwal “${item.title}” pada ${weekdays[item.day_of_week]}?`)) return;
    try {
      await request(`/admin/schedules/${id}`, { method: "DELETE" });
      await loadRoomResources(currentRoomId);
      scheduleMessage("Jadwal dihapus.");
      notifyDataChanged();
    } catch (error) { scheduleMessage(`Gagal menghapus jadwal: ${error.message}`); }
  }

  async function seedSchedules(button) {
    const label = button.textContent;
    button.disabled = true; button.setAttribute("aria-busy", "true"); button.textContent = "Mengisi…";
    try {
      const result = await request("/admin/schedules/seed-sample", { method: "POST" });
      if (currentRoomId) await loadRoomResources(currentRoomId);
      scheduleMessage(`${result.created} jadwal contoh ditambahkan; ${result.skipped_conflicts} dilewati karena bentrok.`);
      notifyDataChanged();
    } catch (error) { scheduleMessage(`Gagal mengisi jadwal: ${error.message}`); }
    finally { button.disabled = false; button.removeAttribute("aria-busy"); button.textContent = label; }
  }

  async function seedUsage(button) {
    const label = button.textContent;
    button.disabled = true; button.setAttribute("aria-busy", "true"); button.textContent = "Mengisi…";
    try {
      const result = await request("/admin/usage-calendar/seed-sample", { method: "POST" });
      scheduleMessage(`${result.created} tanggal riwayat contoh ditambahkan. Data yang sudah ada tetap dipertahankan.`);
      notifyDataChanged();
    } catch (error) { scheduleMessage(`Gagal mengisi riwayat: ${error.message}`); }
    finally { button.disabled = false; button.removeAttribute("aria-busy"); button.textContent = label; }
  }

  async function sendSimulation(button) {
    const rawCount = $("sim-count").value;
    const count = Number(rawCount);
    if (!Number.isInteger(count) || count < 0) { $("sim-msg").textContent = "Jumlah orang harus bilangan bulat minimal 0."; return; }
    button.disabled = true;
    button.setAttribute("aria-busy", "true");
    const label = button.textContent;
    button.textContent = "Mengirim…";
    try {
      const result = await request("/occupancy", {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ room_id: Number($("sim-room").value), person_count: count, source: "dashboard" }),
      });
      $("sim-msg").textContent = result.commands?.length
        ? `Aturan terpicu: ${result.commands.length} perintah ${result.commands[0].action} (${result.commands[0].status}).`
        : "Okupansi tersimpan, aturan belum terpicu.";
      notifyDataChanged();
    } catch (error) { $("sim-msg").textContent = `Gagal mengirim: ${error.message}`; }
    finally { button.disabled = false; button.removeAttribute("aria-busy"); button.textContent = label; }
  }

  async function saveRoom() {
    const name = $("admin-room-name").value.trim();
    const building = $("admin-room-building").value.trim();
    const floor = $("admin-room-floor").value.trim();
    const rawCapacity = $("admin-room-capacity").value;
    if (!name) { roomMessage("Nama atau kode kelas wajib diisi."); return; }
    const body = { name, building: building || null, floor: floor || null, capacity: rawCapacity === "" ? null : Number(rawCapacity) };
    const isNewRoom = !currentRoomId;
    try {
      const saved = currentRoomId
        ? await request(`/admin/rooms/${currentRoomId}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) })
        : await request("/admin/rooms", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
      await loadRooms(saved.id);
      roomMessage(isNewRoom ? "Kelas baru ditambahkan." : "Perubahan kelas tersimpan.");
      notifyDataChanged();
    } catch (error) { roomMessage(`Gagal menyimpan kelas: ${error.message}`); }
  }

  function newDevice() { resetDeviceForm(); $("admin-device-name").focus(); }
  function newCamera() { resetCameraForm(); $("admin-camera-name").focus(); }

  root.addEventListener("input", (event) => {
    if (["admin-lamp-count", "admin-lamp-watt", "admin-ac-count", "admin-ac-watt"].includes(event.target.id)) updateDeviceTypeFields();
  });
  root.addEventListener("change", async (event) => {
    if (event.target.id === "admin-room-select") {
      const value = event.target.value;
      const room = value === "new" ? null : rooms.find((item) => String(item.id) === value) || null;
      fillRoom(room);
      if (room && $("sim-room")) $("sim-room").value = String(room.id);
      if (room) {
        try { await loadRoomResources(room.id); }
        catch (error) { roomMessage(`Gagal memuat data kelas: ${error.message}`); }
      }
    }
    if (event.target.id === "admin-device-type") updateDeviceTypeFields();
  });
  root.addEventListener("click", async (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    if (button.id === "admin-login") {
      const candidate = $("admin-token").value.trim();
      if (!candidate) { authMessage("Token admin wajib diisi."); return; }
      token = candidate;
      await openAdmin();
    } else if (button.id === "admin-logout") {
      token = ""; rooms = []; devices = []; cameras = []; schedules = []; currentRoomId = null;
      sessionStorage.removeItem("hackx.adminToken");
      showSignedIn(false); authMessage("Anda sudah keluar dari admin.");
    } else if (button.id === "sim-send") {
      await sendSimulation(button);
    } else if (button.id === "admin-room-save") {
      await saveRoom();
    } else if (button.id === "admin-device-new") {
      newDevice();
    } else if (button.id === "admin-device-save") {
      await saveDevice();
    } else if (button.id === "admin-device-cancel") {
      resetDeviceForm();
    } else if (button.id === "admin-camera-new") {
      newCamera();
    } else if (button.id === "admin-camera-save") {
      await saveCamera();
    } else if (button.id === "admin-camera-clear-auth") {
      await clearCameraAuth();
    } else if (button.id === "admin-camera-cancel") {
      resetCameraForm();
    } else if (button.id === "admin-schedule-new") {
      resetScheduleForm(); $("admin-schedule-title").focus();
    } else if (button.id === "admin-schedule-save") {
      await saveSchedule();
    } else if (button.id === "admin-schedule-cancel") {
      resetScheduleForm();
    } else if (button.id === "admin-schedule-seed") {
      await seedSchedules(button);
    } else if (button.id === "admin-usage-seed") {
      await seedUsage(button);
    } else if (button.dataset.adminAction === "edit-device") {
      editDevice(Number(button.dataset.id));
    } else if (button.dataset.adminAction === "toggle-device") {
      await toggleDevice(Number(button.dataset.id));
    } else if (button.dataset.adminAction === "edit-camera") {
      editCamera(Number(button.dataset.id));
    } else if (button.dataset.adminAction === "toggle-camera") {
      await toggleCamera(Number(button.dataset.id));
    } else if (button.dataset.adminAction === "edit-schedule") {
      editSchedule(Number(button.dataset.id));
    } else if (button.dataset.adminAction === "delete-schedule") {
      await deleteSchedule(Number(button.dataset.id));
    }
  });

  appStore.subscribe((state, previous) => {
    if (state.route !== previous.route && state.route.name === "admin" && token) openAdmin();
  });
  if (appStore.getState().route.name === "admin" && token) openAdmin();
  else showSignedIn(false);
})();
