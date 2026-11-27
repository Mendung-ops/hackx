let routeController = new AbortController();

export function beginRouteScope() {
  routeController.abort();
  routeController = new AbortController();
  return routeController.signal;
}

export async function api(path, options = {}) {
  const { routeScoped, ...requestOptions } = options;
  const method = String(requestOptions.method || "GET").toUpperCase();
  const headers = { ...(requestOptions.headers || {}) };
  const token = sessionStorage.getItem("hackx.adminToken");
  if (token && method !== "GET") headers["X-Admin-Token"] = token;
  const shouldUseRouteSignal = routeScoped !== false && method === "GET";
  const signal = requestOptions.signal || (shouldUseRouteSignal ? routeController.signal : undefined);
  const response = await fetch(path, { ...requestOptions, headers, ...(signal ? { signal } : {}) });
  if (!response.ok) {
    let detail = "";
    try { detail = (await response.json()).detail || ""; } catch (_) {}
    throw new Error(detail || `${path} → ${response.status}`);
  }
  return response.json();
}

export const isAbortError = (error) => error?.name === "AbortError";
