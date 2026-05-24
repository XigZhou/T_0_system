(function () {
  const state = { user: null, loaded: false, loading: null };

  async function fetchJson(url, options = {}) {
    const response = await fetch(url, { credentials: "same-origin", ...options });
    if (!response.ok) {
      const data = await response.json().catch(() => ({}));
      throw new Error(data.detail || `请求失败：${response.status}`);
    }
    return response.json();
  }

  async function loadCurrentUser() {
    if (state.loaded) return state.user;
    if (state.loading) return state.loading;
    state.loading = fetchJson("/api/auth/me")
      .then((data) => {
        state.user = data.authenticated ? data.user : null;
        state.loaded = true;
        return state.user;
      })
      .finally(() => {
        state.loading = null;
      });
    return state.loading;
  }

  function currentUsername() {
    return state.user?.username || "admin";
  }

  function isAdmin() {
    return state.user?.role === "admin";
  }

  async function logout() {
    await fetchJson("/api/auth/logout", { method: "POST" });
    window.location.href = "/login";
  }

  async function hydratePage() {
    const user = await loadCurrentUser();
    document.querySelectorAll("[data-current-user]").forEach((el) => {
      el.textContent = user?.username || "未登录";
    });
    document.querySelectorAll("[data-admin-only]").forEach((el) => {
      el.hidden = !isAdmin();
    });
    document.querySelectorAll("[data-logout]").forEach((el) => {
      el.addEventListener("click", (event) => {
        event.preventDefault();
        logout().catch(() => {
          window.location.href = "/login";
        });
      });
    });
  }

  window.T0Auth = { fetchJson, loadCurrentUser, currentUsername, isAdmin, logout, hydratePage };
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", () => hydratePage().catch(() => {}));
  } else {
    hydratePage().catch(() => {});
  }
})();
