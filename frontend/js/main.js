// Titik masuk dan penjadwal tugas berkala dashboard.
import { handleRoute, loadApiVersion, loadSchedules, loadUsageCalendar, refresh } from "./app.js";
import { beginRouteScope } from "./api.js";
import { startRouter } from "./router.js";
import { createScheduler } from "./scheduler.js";
import { appStore } from "./store.js";
import "./usage-overview.js";
import "./admin.js";

const currentRoute = () => appStore.getState().route;
const dashboardRoutes = new Set(["home", "room", "summary"]);
const scheduler = createScheduler({
  getRoute: currentRoute,
  tasks: [
    { interval: 10000, isActive: (route) => route.name !== "not-found", run: () => refresh() },
    { interval: 60000, isActive: (route) => route.name !== "not-found", run: () => loadSchedules(true) },
    { interval: 300000, isActive: (route) => dashboardRoutes.has(route.name), run: (route) => loadUsageCalendar(route.name, true) },
    { interval: 300000, isActive: (route) => route.name === "summary", run: () => window.UsageOverview?.reload() },
  ],
});

startRouter(handleRoute, { beginRouteScope });
scheduler.start();
loadApiVersion();
window.addEventListener("hackx:data-changed", () => scheduler.runActive({ force: true }));
