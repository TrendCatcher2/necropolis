// Lantern Lane front end v2 (fictional demo shop; all data is fake).
// Calls only the v2 API, which requires a token. The v1 API is no longer referenced here.
let token = null;

const api = {
  signIn: () => fetch("/api/v2/session", { method: "POST" }).then((r) => r.json()),
  user: (id) =>
    fetch(`/api/v2/users/${id}`, { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.json()),
  orders: () =>
    fetch("/api/v2/orders", { headers: { Authorization: `Bearer ${token}` } }).then((r) => r.json()),
};

function show(id, text) {
  document.getElementById(id).textContent = text;
}

window.addEventListener("DOMContentLoaded", () => {
  document.getElementById("signin").addEventListener("click", async () => {
    try {
      token = (await api.signIn()).token;
      const me = await api.user(1);
      show("name", me.data.name);
      const orders = await api.orders();
      show("orders", `${orders.data.length} orders`);
    } catch (e) {
      show("name", "sign-in failed");
    }
  });
});
