(() => {
  const form = document.querySelector("#login-form");
  const error = document.querySelector("#login-error");

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const submit = form.querySelector("button[type=submit]");
    submit.disabled = true;
    const data = new FormData(form);
    try {
      const response = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: data.get("username"),
          password: data.get("password"),
        }),
      });
      if (!response.ok) {
        error.textContent = response.status === 401
          ? "Usuário ou senha inválidos."
          : "Não foi possível entrar.";
        error.hidden = false;
        return;
      }
      const body = await response.json();
      location.assign(body.user.role === "gm" ? "/" : "/player");
    } catch (_err) {
      error.textContent = "O Loremaster não respondeu.";
      error.hidden = false;
    } finally {
      submit.disabled = false;
    }
  });
})();
