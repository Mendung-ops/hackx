import test from "node:test";
import assert from "node:assert/strict";
import { createScheduler } from "../js/scheduler.js";

test("scheduler menjalankan tugas aktif sesuai interval dan menghentikannya saat tab tersembunyi", async () => {
  let now = 0;
  let tick;
  let runCount = 0;
  const listeners = new Map();
  const documentRef = {
    hidden: false,
    addEventListener(name, callback) { listeners.set(name, callback); },
    removeEventListener(name) { listeners.delete(name); },
  };
  const windowRef = { setInterval(callback) { tick = callback; return 1; }, clearInterval() {} };
  const scheduler = createScheduler({
    documentRef,
    windowRef,
    now: () => now,
    getRoute: () => ({ name: "home" }),
    tasks: [{ interval: 100, run() { runCount += 1; } }],
  });
  scheduler.start();
  now = 99;
  tick();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(runCount, 0);
  now = 100;
  tick();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(runCount, 1);
  documentRef.hidden = true;
  now = 200;
  tick();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(runCount, 1);
  scheduler.stop();
  assert.equal(listeners.has("visibilitychange"), false);
});
