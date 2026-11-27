import { api, isAbortError } from "./api.js";
import { appStore } from "./store.js";

(() => {
  const escapeHtml = (value) => String(value ?? "").replace(/[&<>"']/g, (char) => ({
    "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;",
  }[char]));
  const format = (value, digits = 1) => Number(value || 0).toLocaleString("id-ID", { maximumFractionDigits: digits });
  const dateLabel = (value, options = { day: "numeric", month: "short" }) => {
    const date = new Date(String(value) + "T00:00:00");
    return Number.isNaN(date.getTime()) ? escapeHtml(value) : date.toLocaleDateString("id-ID", options);
  };
  const days = ["Senin", "Selasa", "Rabu", "Kamis", "Jumat", "Sabtu", "Minggu"];
  const periodLabels = { "7d": "7 hari", "30d": "30 hari", "6m": "6 bulan" };
  const state = { period: "7d", data: null, loadedAt: 0, request: null, requestPeriod: "", sort: "idle_energy_kwh", direction: -1 };

  function setStatuses(message) {
    ["overview-status", "trend-status", "rooms-status", "hour-status"].forEach((id) => {
      const node = document.getElementById(id);
      if (node) node.textContent = message;
    });
  }

  function changeMarkup(value, metric) {
    if (value === null || value === undefined) return '<span class="change neutral">Belum ada pembanding</span>';
    const up = value > 0, down = value < 0;
    const arrow = up ? "▲" : down ? "▼" : "•";
    const direction = up ? "naik" : down ? "turun" : "tetap";
    let tone = "neutral";
    if (metric === "utilization_pct") tone = up ? "positive" : down ? "caution" : "neutral";
    else if (metric === "idle_energy_kwh_pct" || metric === "energy_kwh_pct") tone = up ? "caution" : down ? "positive" : "neutral";
    return '<span class="change ' + tone + '">' + arrow + " " + direction + " " + format(Math.abs(value), 1) + '% dibanding periode sebelumnya</span>';
  }

  function renderCards(data) {
    const totals = data.current.totals;
    if (!data.rooms?.length) {
      document.getElementById("overview-stats").innerHTML = "";
      document.getElementById("overview-status").textContent = "Belum ada ruang terdaftar.";
      document.getElementById("overview-dummy-note").hidden = true;
      return;
    }
    const cards = [
      ["Energi (estimasi)", format(totals.energy_kwh, 2) + " kWh", data.changes.energy_kwh_pct, "energy_kwh_pct"],
      ["Waktu ruang terisi", format(totals.occupied_hours, 1) + " jam", data.changes.occupied_hours_pct, "occupied_hours_pct"],
      ["Utilisasi jadwal", totals.utilization_pct === null ? "–" : format(totals.utilization_pct, 1) + "%", data.changes.utilization_pct, "utilization_pct"],
      ["Energi terbuang saat ruang kosong", format(totals.idle_energy_kwh, 2) + " kWh", data.changes.idle_energy_kwh_pct, "idle_energy_kwh_pct"],
    ];
    document.getElementById("overview-stats").innerHTML = cards.map((item) =>
      '<article class="card stat overview-stat"><small>' + escapeHtml(item[0]) + '</small><b>' + escapeHtml(item[1]) + '</b>' + changeMarkup(item[2], item[3]) + '</article>'
    ).join("");
    const status = document.getElementById("overview-status");
    status.textContent = totals.utilization_pct === null
      ? "Periode " + periodLabels[data.period] + "; belum ada jadwal aktif untuk menghitung utilisasi."
      : "Periode " + periodLabels[data.period] + " · " + dateLabel(data.current.from, { day: "numeric", month: "short", year: "numeric" }) + "–" + dateLabel(data.current.to, { day: "numeric", month: "short", year: "numeric" }) + ".";
    const note = document.getElementById("overview-dummy-note");
    note.hidden = !data.has_dummy;
    note.textContent = data.has_dummy ? "Riwayat sebelum sistem berjalan adalah data contoh." : "";
  }

  function renderTrend(data) {
    const status = document.getElementById("trend-status");
    const root = document.getElementById("usage-trend");
    const series = data.current.series || [];
    if (!data.rooms?.length || !series.length) {
      status.textContent = data.rooms?.length ? "Belum ada data untuk periode ini." : "Belum ada data ruang.";
      root.innerHTML = "";
      return;
    }
    status.textContent = "";
    const width = 820, height = 270;
    const pad = { left: 58, right: 20, top: 22, bottom: 46 };
    const plotWidth = width - pad.left - pad.right;
    const plotHeight = height - pad.top - pad.bottom;
    const maxValue = Math.max(0.01, ...series.flatMap((item) => [item.energy_kwh, item.idle_energy_kwh]));
    const x = (index) => pad.left + (series.length < 2 ? plotWidth / 2 : index * plotWidth / (series.length - 1));
    const y = (value) => pad.top + plotHeight - (value / maxValue) * plotHeight;
    const totalPoints = series.map((item, index) => x(index).toFixed(1) + "," + y(item.energy_kwh).toFixed(1)).join(" ");
    const idlePoints = series.map((item, index) => x(index).toFixed(1) + "," + y(item.idle_energy_kwh).toFixed(1)).join(" ");
    const ticks = [0, maxValue / 2, maxValue];
    const guides = ticks.map((tick) => '<g><line x1="' + pad.left + '" y1="' + y(tick) + '" x2="' + (width - pad.right) + '" y2="' + y(tick) + '" class="chart-gridline"/><text x="' + (pad.left - 8) + '" y="' + (y(tick) + 4) + '" text-anchor="end" class="chart-label">' + escapeHtml(format(tick, 1)) + '</text></g>').join("");
    const labelIndexes = [...new Set([0, Math.floor((series.length - 1) / 2), series.length - 1])];
    const labels = labelIndexes.map((index) => {
      const anchor = index === 0 ? "start" : index === series.length - 1 ? "end" : "middle";
      return '<text x="' + x(index) + '" y="' + (height - 13) + '" text-anchor="' + anchor + '" class="chart-label">' + escapeHtml(dateLabel(series[index].date)) + '</text>';
    }).join("");
    const dots = series.map((item, index) => {
      const label = dateLabel(item.date, { day: "numeric", month: "long", year: "numeric" }) + " · Energi " + format(item.energy_kwh, 2) + " kWh · Energi terbuang " + format(item.idle_energy_kwh, 2) + " kWh";
      const safe = escapeHtml(label);
      const totalLabel = escapeHtml(dateLabel(item.date) + " · Energi total " + format(item.energy_kwh, 2) + " kWh");
      const idleLabel = escapeHtml(dateLabel(item.date) + " · Energi terbuang " + format(item.idle_energy_kwh, 2) + " kWh");
      return '<circle cx="' + x(index) + '" cy="' + y(item.energy_kwh) + '" r="4" class="chart-dot total-dot" tabindex="0" role="img" aria-label="' + totalLabel + '"><title>' + totalLabel + '</title></circle>' +
        '<circle cx="' + x(index) + '" cy="' + y(item.idle_energy_kwh) + '" r="4" class="chart-dot idle-dot" tabindex="0" role="img" aria-label="' + idleLabel + '"><title>' + idleLabel + '</title></circle>';
    }).join("");
    root.innerHTML = '<svg class="usage-trend-svg" viewBox="0 0 ' + width + " " + height + '" role="img" aria-label="Grafik energi total dan energi saat ruang kosong pada ' + escapeHtml(periodLabels[data.period]) + ' terakhir. Sumbu energi dimulai dari nol.">' +
      guides + '<text x="12" y="16" class="chart-label">kWh</text><line x1="' + pad.left + '" y1="' + (pad.top + plotHeight) + '" x2="' + (width - pad.right) + '" y2="' + (pad.top + plotHeight) + '" class="chart-axis"/>' +
      '<polyline points="' + totalPoints + '" class="chart-line total-line"/><polyline points="' + idlePoints + '" class="chart-line idle-line"/>' + dots + labels + '</svg>' +
      '<div class="chart-legend"><span><i class="legend-total"></i>Energi total</span><span><i class="legend-idle"></i>Energi saat ruang kosong</span></div>';
  }

  function renderRooms(data) {
    const status = document.getElementById("rooms-status");
    const root = document.getElementById("usage-room-table");
    if (!data.rooms?.length) {
      status.textContent = "Belum ada data ruang.";
      root.innerHTML = "";
      return;
    }
    status.textContent = "";
    const titles = {
      name: "Ruang", occupied_hours: "Jam terisi", scheduled_hours: "Jam terjadwal",
      utilization_pct: "Utilisasi", energy_kwh: "Energi", idle_energy_kwh: "Energi saat kosong",
    };
    const rows = [...data.rooms].sort((a, b) => {
      const left = a[state.sort], right = b[state.sort];
      if (left === null || left === undefined) return 1;
      if (right === null || right === undefined) return -1;
      return (typeof left === "string" ? left.localeCompare(right, "id") : left - right) * state.direction;
    });
    const headers = Object.entries(titles).map(([key, title]) => {
      const direction = state.sort === key ? (state.direction < 0 ? " menurun" : " menaik") : "";
      const arrow = state.sort === key ? (state.direction < 0 ? " ↓" : " ↑") : "";
      const ariaSort = state.sort === key ? (state.direction < 0 ? "descending" : "ascending") : "none";
      return '<th scope="col" aria-sort="' + ariaSort + '"><button type="button" class="table-sort" data-room-sort="' + key + '" aria-label="Urutkan berdasarkan ' + escapeHtml(title) + direction + '">' + escapeHtml(title) + arrow + '</button></th>';
    }).join("");
    const body = rows.map((room) => {
      const id = Number(room.room_id);
      const utilization = room.utilization_pct === null ? '<span title="Tanpa jadwal">–</span>' : format(room.utilization_pct, 1) + "%";
      return '<tr class="usage-room-row" data-room-link="' + id + '" tabindex="0" role="link" aria-label="' + escapeHtml(room.name) + '; buka detail ruang"><td>' + escapeHtml(room.name) + "</td><td>" + format(room.occupied_hours, 1) + "</td><td>" + format(room.scheduled_hours, 1) + "</td><td>" + utilization + "</td><td>" + format(room.energy_kwh, 2) + " kWh</td><td>" + format(room.idle_energy_kwh, 2) + " kWh</td></tr>";
    }).join("");
    root.innerHTML = "<table><thead><tr>" + headers + "</tr></thead><tbody>" + body + "</tbody></table>";
  }

  function renderHourHeatmap(data) {
    const status = document.getElementById("hour-status");
    const root = document.getElementById("usage-hour-heatmap");
    if (!data.rooms?.length || !data.hour_heatmap?.length) {
      status.textContent = data.rooms?.length ? "Belum ada data profil per jam." : "Belum ada data ruang.";
      root.innerHTML = "";
      return;
    }
    status.textContent = "";
    let cells = '<div class="hour-day-label" aria-hidden="true"></div>';
    for (let hour = 0; hour < 24; hour++) cells += '<span class="hour-label">' + String(hour).padStart(2, "0") + "</span>";
    for (let dayIndex = 0; dayIndex < data.hour_heatmap.length; dayIndex++) {
      cells += '<div class="hour-day-label">' + days[dayIndex] + "</div>";
      const dayCells = data.hour_heatmap[dayIndex];
      for (let hour = 0; hour < dayCells.length; hour++) {
        const cell = dayCells[hour];
        const label = days[dayIndex] + " " + String(hour).padStart(2, "0") + ":00 · rata-rata " + format(cell.average_occupied_minutes, 0) + " menit terisi";
        const safe = escapeHtml(label);
        cells += '<span class="hour-heat-cell heat-' + Number(cell.level) + '" tabindex="0" role="img" title="' + safe + '" aria-label="' + safe + '"></span>';
      }
    }
    root.innerHTML = '<div class="hour-heat-scroll" tabindex="0" aria-label="Heatmap jam sibuk, Senin sampai Minggu"><div class="hour-heat-grid" style="grid-template-columns:48px repeat(24, minmax(18px, 1fr))">' + cells + '</div></div>' +
      '<div class="heatmap-legend"><span>Sedikit</span>' + [0, 1, 2, 3, 4].map((level) => '<span class="heat-day heat-' + level + '" aria-hidden="true"></span>').join("") + '<span>Banyak</span></div>';
  }

  function render(data) {
    document.querySelectorAll("[data-overview-period]").forEach((button) => {
      button.setAttribute("aria-pressed", String(button.dataset.overviewPeriod === state.period));
    });
    renderCards(data);
    renderTrend(data);
    renderRooms(data);
    renderHourHeatmap(data);
  }

  async function load(force = false) {
    if (appStore.getState().route.name !== "summary") return null;
    if (state.request) {
      if (state.requestPeriod === state.period) return state.request;
      return state.request.then(() => load(true));
    }
    if (!force && state.data && Date.now() - state.loadedAt < 300000) {
      render(state.data);
      return state.data;
    }
    setStatuses("Memuat ringkasan…");
    const requestedPeriod = state.period;
    let aborted = false;
    state.requestPeriod = requestedPeriod;
    state.request = (async () => {
      try {
        const data = await api("/dashboard/usage-overview?period=" + encodeURIComponent(requestedPeriod));
        if (state.period !== requestedPeriod) return null;
        state.data = data;
        state.loadedAt = Date.now();
        render(data);
        return data;
      } catch (error) {
        if (isAbortError(error)) { aborted = true; return null; }
        state.data = null;
        state.loadedAt = 0;
        const message = "Gagal memuat: " + escapeHtml(error.message);
        setStatuses(message);
        document.getElementById("usage-trend").innerHTML = "";
        document.getElementById("usage-room-table").innerHTML = "";
        document.getElementById("usage-hour-heatmap").innerHTML = "";
        document.getElementById("overview-stats").innerHTML = "";
        document.getElementById("overview-dummy-note").hidden = true;
        return null;
      } finally {
        state.request = null;
        state.requestPeriod = "";
        if (aborted && appStore.getState().route.name === "summary" && !document.hidden) queueMicrotask(() => load(true));
      }
    })();
    return state.request;
  }

  document.addEventListener("click", (event) => {
    const periodButton = event.target.closest("[data-overview-period]");
    if (periodButton) {
      if (state.period === periodButton.dataset.overviewPeriod) return;
      state.period = periodButton.dataset.overviewPeriod;
      state.data = null;
      state.loadedAt = 0;
      load(true);
      return;
    }
    const sortButton = event.target.closest("[data-room-sort]");
    if (sortButton && state.data) {
      const key = sortButton.dataset.roomSort;
      if (state.sort === key) state.direction *= -1;
      else {
        state.sort = key;
        state.direction = key === "name" ? 1 : -1;
      }
      renderRooms(state.data);
      return;
    }
    const row = event.target.closest("[data-room-link]");
    if (row) location.hash = "#/ruang/" + Number(row.dataset.roomLink);
  });
  document.addEventListener("keydown", (event) => {
    const row = event.target.closest("[data-room-link]");
    if (row && (event.key === "Enter" || event.key === " ")) {
      event.preventDefault();
      location.hash = "#/ruang/" + Number(row.dataset.roomLink);
    }
  });
  window.UsageOverview = { onShow: () => load(false), reload: () => load(true) };
})();
