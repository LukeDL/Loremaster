(() => {
  const list = document.querySelector("#users-list");
  const form = document.querySelector("#create-player");
  const error = document.querySelector("#create-error");
  const createDialog = document.querySelector("#create-player-dialog");
  const passwordDialog = document.querySelector("#password-dialog");
  const passwordForm = document.querySelector("#password-form");
  const passwordTitle = document.querySelector("#password-dialog-title");
  const passwordError = document.querySelector("#password-error");
  const statusDialog = document.querySelector("#status-dialog");
  const statusForm = document.querySelector("#status-form");
  const statusDescription = document.querySelector("#status-dialog-description");
  const statusError = document.querySelector("#status-error");
  const notice = document.querySelector("#users-notice");
  const openCreateButton = document.querySelector("#open-create-player");
  let passwordUser = null;
  let statusUser = null;
  let noticeTimer = null;

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

  function showDialog(dialog) {
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeDialog(dialog) {
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  function showNotice(message) {
    window.clearTimeout(noticeTimer);
    notice.textContent = message;
    notice.hidden = false;
    noticeTimer = window.setTimeout(() => { notice.hidden = true; }, 5000);
  }

  function openPasswordDialog(user) {
    passwordUser = user;
    passwordForm.reset();
    passwordError.hidden = true;
    passwordTitle.textContent = `Redefinir senha de ${user.username}`;
    showDialog(passwordDialog);
  }

  function openStatusDialog(user) {
    statusUser = user;
    statusError.hidden = true;
    statusDescription.textContent = `${user.username} perderá o acesso imediatamente e suas sessões serão encerradas.`;
    showDialog(statusDialog);
  }

  async function setUserActive(user, isActive) {
    const response = await request(`/api/admin/users/${user.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ is_active: isActive }),
    });
    if (!response.ok) throw new Error("Não foi possível alterar o acesso desse jogador.");
  }

  async function loadUsers() {
    const response = await request("/api/admin/users");
    if (!response.ok) throw new Error("Não foi possível carregar os usuários.");
    const users = await response.json();
    list.replaceChildren();
    for (const user of users) {
      const card = document.createElement("article");
      card.className = `user-card${user.is_active ? "" : " inactive"}`;
      const identity = document.createElement("div");
      identity.className = "user-identity";
      const avatar = document.createElement("div");
      avatar.className = "user-avatar";
      avatar.textContent = user.username.slice(0, 1).toUpperCase();
      const details = document.createElement("div");
      const name = document.createElement("strong");
      name.textContent = user.username;
      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = user.role === "gm" ? "Mestre" : "Jogador";
      details.append(name, meta);
      identity.append(avatar, details);

      const badge = document.createElement("span");
      badge.className = user.is_active ? "user-status active" : "user-status";
      badge.textContent = user.is_active ? "ativo" : "desativado";

      const actions = document.createElement("div");
      actions.className = "actions";
      if (user.role === "player") {
        actions.append(
          button("redefinir senha", () => openPasswordDialog(user)),
          button(user.is_active ? "desativar" : "ativar", async () => {
            if (user.is_active) {
              openStatusDialog(user);
              return;
            }
            try {
              await setUserActive(user, true);
              showNotice(`${user.username} foi ativado.`);
              await loadUsers();
            } catch (reason) {
              showNotice(reason.message || "Não foi possível ativar o jogador.");
            }
          }, user.is_active ? "danger-ghost" : "primary"),
        );
      }
      const heading = document.createElement("div");
      heading.className = "user-card-heading";
      heading.append(identity, badge);
      card.append(heading, actions);
      list.append(card);
    }
  }

  openCreateButton.addEventListener("click", () => {
    form.reset();
    error.hidden = true;
    showDialog(createDialog);
  });

  for (const dialog of [createDialog, passwordDialog, statusDialog]) {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) closeDialog(dialog);
    });
    for (const closeButton of dialog.querySelectorAll("[data-close-dialog]")) {
      closeButton.addEventListener("click", () => closeDialog(dialog));
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
    closeDialog(createDialog);
    showNotice("Conta de jogador criada.");
    await loadUsers();
  });

  passwordForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    passwordError.hidden = true;
    if (!passwordUser) return;
    const data = new FormData(passwordForm);
    const response = await request(`/api/admin/users/${passwordUser.id}/password`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ password: data.get("password") }),
    });
    if (!response.ok) {
      passwordError.textContent = "Não foi possível redefinir a senha.";
      passwordError.hidden = false;
      return;
    }
    const username = passwordUser.username;
    passwordUser = null;
    passwordForm.reset();
    closeDialog(passwordDialog);
    showNotice(`Senha de ${username} redefinida; sessões anteriores encerradas.`);
  });

  statusForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    statusError.hidden = true;
    if (!statusUser) return;
    try {
      await setUserActive(statusUser, false);
      const username = statusUser.username;
      statusUser = null;
      closeDialog(statusDialog);
      showNotice(`${username} foi desativado.`);
      await loadUsers();
    } catch (reason) {
      statusError.textContent = reason.message || "Não foi possível desativar o jogador.";
      statusError.hidden = false;
    }
  });

  loadUsers().catch((reason) => {
    list.textContent = reason.message || "Não foi possível carregar os usuários.";
  }).finally(() => {
    openCreateButton.disabled = false;
  });
})();
