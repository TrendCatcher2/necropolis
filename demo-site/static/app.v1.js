// Lantern Lane front end v1 (fictional demo shop; all data is fake).
// Calls the v1 API. Archived with Save Page Now before the switch to v2.
const api = {
  user: (id) => fetch(`/api/v1/users/${id}`).then((r) => r.json()),
  orders: () => fetch("/api/v1/orders"),
  status: () => fetch("/api/v1/status").then((r) => r.json()),
  exportAll: () => fetch("/api/v1/legacy-export"),
  // Left over from development: only called when the page is opened with ?debug=1.
  debugTrace: () => fetch("/api/v1/debug/trace").then((r) => r.text()),
};

function show(id, text) {
  document.getElementById(id).textContent = text;
}

window.addEventListener("DOMContentLoaded", async () => {
  if (new URLSearchParams(window.location.search).has("debug")) {
    api.debugTrace().then((t) => console.log(t));
  }
  try {
    const me = await api.user(1);
    show("name", me.data.name);
    show("email", me.data.email);
  } catch (e) {
    show("name", "unavailable");
  }
  try {
    const s = await api.status();
    show("status", s.status);
  } catch (e) {
    show("status", "unknown");
  }
});
