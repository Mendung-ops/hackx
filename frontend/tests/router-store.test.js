import test from "node:test";
import assert from "node:assert/strict";
import { parseRoute, startRouter } from "../js/router.js";
import { createStore } from "../js/store.js";

test("router mengenali rute yang tersedia dan alias ringkasan", () => {
  assert.deepEqual(parseRoute("#/"), { name: "home" });
  assert.deepEqual(parseRoute("#/ruang/12"), { name: "room", id: 12 });
  assert.deepEqual(parseRoute("#/admin"), { name: "admin" });
  assert.deepEqual(parseRoute("#/penggunaan"), { name: "summary" });
  assert.deepEqual(parseRoute("#/ringkasan"), { name: "summary", redirect: true });
  assert.deepEqual(parseRoute("#/alamat-lain"), { name: "not-found" });
});

test("store menyimpan state bersama dan memberi tahu subscriber", () => {
  const store = createStore({ count: 0 });
  const updates = [];
  const unsubscribe = store.subscribe((state, previous) => updates.push([state.count, previous.count]));
  store.setState({ count: 1 });
  unsubscribe();
  store.setState({ count: 2 });
  assert.equal(store.getState().count, 2);
  assert.deepEqual(updates, [[1, 0]]);
});


test("router mengalihkan alias lama tanpa menambahkan entri riwayat", () => {
  const handlers = {};
  const location = { hash: "#/ringkasan", pathname: "/ui/", search: "" };
  let replaceCalls = 0;
  let routeScopeCalls = 0;
  let receivedRoute;
  const windowRef = {
    location,
    history: { replaceState(_state, _title, url) { replaceCalls += 1; location.hash = url.slice(url.indexOf("#")); } },
    addEventListener(name, handler) { handlers[name] = handler; },
    removeEventListener(name) { delete handlers[name]; },
  };
  const stop = startRouter((route) => { receivedRoute = route; }, { windowRef, beginRouteScope() { routeScopeCalls += 1; } });
  assert.equal(location.hash, "#/penggunaan");
  assert.deepEqual(receivedRoute, { name: "summary" });
  assert.equal(replaceCalls, 1);
  assert.equal(routeScopeCalls, 1);
  stop();
  assert.equal(handlers.hashchange, undefined);
});
