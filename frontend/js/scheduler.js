export function createScheduler({ tasks, getRoute, documentRef = document, windowRef = window, now = () => Date.now() }) {
  const states = tasks.map((task) => ({ task, lastRun: now(), inFlight: false, rerun: false }));
  let timer = null;

  function isActive(task) {
    return !task.isActive || task.isActive(getRoute());
  }

  async function runTask(state, force = false) {
    if (documentRef.hidden || !isActive(state.task)) return;
    if (!force && now() - state.lastRun < state.task.interval) return;
    if (state.inFlight) {
      if (force) state.rerun = true;
      return;
    }
    state.inFlight = true;
    state.lastRun = now();
    try {
      await state.task.run(getRoute());
    } catch (_) {
      // Tiap tugas menangani pesan galatnya sendiri; timer tetap berjalan.
    } finally {
      state.inFlight = false;
      if (state.rerun && !documentRef.hidden && isActive(state.task)) {
        state.rerun = false;
        queueMicrotask(() => runTask(state, true));
      }
    }
  }

  function runActive({ force = false } = {}) {
    return Promise.all(states.filter((state) => isActive(state.task)).map((state) => runTask(state, force)));
  }

  function tick() {
    for (const state of states) void runTask(state);
  }

  function onVisibilityChange() {
    if (!documentRef.hidden) void runActive({ force: true });
  }

  function start() {
    if (timer !== null) return;
    timer = windowRef.setInterval(tick, 1000);
    documentRef.addEventListener("visibilitychange", onVisibilityChange);
  }

  function stop() {
    if (timer === null) return;
    windowRef.clearInterval(timer);
    timer = null;
    documentRef.removeEventListener("visibilitychange", onVisibilityChange);
  }

  return { start, stop, runActive };
}
