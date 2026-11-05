(() => {
  const list = document.querySelector("#users-list");
  const form = document.querySelector("#create-player");
  const error = document.querySelector("#create-error");

  async function request(url, options = {}) {
    const response = await fetch(url, options);
    if (response.status === 403) throw new Error("Acesso exclusivo do Mestre.");
    return response;
  }

  function button(label, action, className = "") {
    const element = document.createElement("button");
    element.type = "button";
    element.textContent = label;
    element.className = className;
    element.addEventListener("click", action);
    return element;
  }

  async function loadUsers() {
    const response = await request("/api/admin/users");
    if (!response.ok) throw new Error("Não foi possível carregar os usuários.");
    const users = await response.json();
    list.replaceChildren();
    for (const user of users) {
      const row = document.createElement("div");
      row.className = "user-row";
      const identity = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = user.username;
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = `${user.role === "gm" ? "Mestre" : "Jogador"} · ${user.is_active ? "ativo" : "desativado"}`;
      identity.append(name, meta);

      const actions = document.createElement("div");
      actions.className = "actions";
      if (user.role === "player") {
        actions.append(
          button(user.is_active ? "desativar" : "ativar", async () => {
            const response = await request(`/api/admin/users/${user.id}`, {
              method: "PATCH",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ is_active: !user.is_active }),
            });
            if (!response.ok) return alert(await response.text());
            await loadUsers();
          }),
          button("redefinir senha", async () => {
            const password = prompt(`Nova senha temporária para ${user.username} (mínimo 10 caracteres):`);
            if (!password) return;
            const response = await request(`/api/admin/users/${user.id}/password`, {
              method: "PUT",
              headers: { "Content-Type": "application/json" },
              body: JSON.stringify({ password }),
            });
            if (!response.ok) return alert(await response.text());
            alert("Senha redefinida e sessões anteriores encerradas.");
          }),
        );
      }
      row.append(identity, actions);
      list.append(row);
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const data = new FormData(form);
    const response = await request("/api/admin/users", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        username: data.get("username"),
        password: data.get("password"),
        role: "player",
      }),
    });
    if (!response.ok) {
      error.textContent = response.status === 409
        ? "Esse usuário já existe."
        : "Não foi possível criar a conta.";
      error.hidden = false;
      return;
    }
    form.reset();
    await loadUsers();
  });

  loadUsers().catch((reason) => {
    list.textContent = reason.message || "Não foi possível carregar os usuários.";
  });
})();
