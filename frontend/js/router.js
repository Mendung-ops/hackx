export function parseRoute(hash = "") {
  if (!hash || hash === "#/") return { name: "home" };
  const room = hash.match(/^#\/ruang\/(\d+)$/);
  if (room) return { name: "room", id: Number(room[1]) };
  if (hash === "#/admin") return { name: "admin" };
  if (hash === "#/penggunaan") return { name: "summary" };
  if (hash === "#/ringkasan") return { name: "summary", redirect: true };
  return { name: "not-found" };
}

export function startRouter(onNavigate, { windowRef = window, beginRouteScope = () => {} } = {}) {
  let currentKey = null;
  const navigate = () => {
    let next = parseRoute(windowRef.location.hash);
    if (next.redirect) {
      const { pathname, search } = windowRef.location;
      windowRef.history.replaceState(null, "", `${pathname}${search}#/penggunaan`);
      next = parseRoute(windowRef.location.hash);
    }
    const key = `${next.name}:${next.id ?? ""}`;
    if (key === currentKey) return;
    currentKey = key;
    beginRouteScope();
    onNavigate(next);
  };
  windowRef.addEventListener("hashchange", navigate);
  navigate();
  return () => windowRef.removeEventListener("hashchange", navigate);
}
