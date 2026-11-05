// Shared cookie-session helpers for the no-build frontend.
(() => {
  const nativeFetch = window.fetch.bind(window);
  const unsafe = new Set(["POST", "PUT", "PATCH", "DELETE"]);

  function cookie(name) {
    const prefix = `${encodeURIComponent(name)}=`;
    const part = document.cookie.split("; ").find((item) => item.startsWith(prefix));
    return part ? decodeURIComponent(part.slice(prefix.length)) : null;
  }

  window.fetch = async (input, init = {}) => {
    const request = input instanceof Request ? input : null;
    const method = String(init.method || request?.method || "GET").toUpperCase();
    const url = new URL(request?.url || input, location.href);
    const headers = new Headers(init.headers || request?.headers || {});
    if (url.origin === location.origin && unsafe.has(method)) {
      const csrf = cookie("loremaster_csrf");
      if (csrf) headers.set("X-CSRF-Token", csrf);
    }
    const response = await nativeFetch(input, { ...init, headers });
    if (response.status === 401 && location.pathname !== "/login") {
      location.assign("/login");
    }
    return response;
  };

  window.LoremasterAuth = {
    async logout() {
      const response = await window.fetch("/api/auth/logout", { method: "POST" });
      if (response.ok) location.assign("/login");
    },
  };
})();
