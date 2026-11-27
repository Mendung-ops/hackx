export function createStore(initialState = {}) {
  let state = { ...initialState };
  const subscribers = new Set();

  return {
    getState() { return state; },
    setState(patch) {
      const previous = state;
      state = { ...state, ...patch };
      for (const subscriber of subscribers) subscriber(state, previous);
      return state;
    },
    subscribe(subscriber) {
      subscribers.add(subscriber);
      return () => subscribers.delete(subscriber);
    },
  };
}

export const appStore = createStore({
  route: { name: "home" },
  overview: null,
  health: null,
  energy: null,
  commands: [],
  occupancyByRoom: {},
  schedules: [],
  errors: [],
  lastUpdatedAt: null,
  usageCalendars: {},
});
