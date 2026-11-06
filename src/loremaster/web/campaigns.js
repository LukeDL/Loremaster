(() => {
  const form = document.querySelector("#create-campaign");
  const error = document.querySelector("#create-campaign-error");
  const packSelect = form.elements.rule_pack_id;
  const createMembers = document.querySelector("#create-members");
  const list = document.querySelector("#campaigns-list");
  const createDialog = document.querySelector("#create-campaign-dialog");
  const membersDialog = document.querySelector("#members-dialog");
  const membersForm = document.querySelector("#members-form");
  const membersTitle = document.querySelector("#members-dialog-title");
  const membersError = document.querySelector("#members-error");
  const editMembers = document.querySelector("#edit-members");
  const settingsDialog = document.querySelector("#settings-dialog");
  const settingsForm = document.querySelector("#settings-form");
  const settingsTitle = document.querySelector("#settings-dialog-title");
  const settingsError = document.querySelector("#settings-error");
  const lifecycleDialog = document.querySelector("#lifecycle-dialog");
  const lifecycleForm = document.querySelector("#lifecycle-form");
  const lifecycleTitle = document.querySelector("#lifecycle-dialog-title");
  const lifecycleDescription = document.querySelector("#lifecycle-description");
  const lifecycleConfirm = document.querySelector("#lifecycle-confirm");
  const lifecycleError = document.querySelector("#lifecycle-error");
  const rosterDialog = document.querySelector("#roster-dialog");
  const rosterTitle = document.querySelector("#roster-dialog-title");
  const rosterList = document.querySelector("#roster-list");
  const openCreateButton = document.querySelector("#open-create-campaign");
  let players = [];
  let currentCampaign = null;
  let lifecycleAction = null;

  const lifecycleLabels = {
    planning: "planejamento",
    in_progress: "em andamento",
    completed: "concluída",
  };
  const statusLabels = { draft: "rascunho", active: "ativo", dead: "morto", retired: "retirado" };

  async function request(url, options = {}) {
    const response = await fetch(url, options);
    if (response.status === 403) throw new Error("Acesso exclusivo do Mestre.");
    return response;
  }

  function actionButton(label, action, className = "") {
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

  function memberOptions(container, selected = []) {
    const chosen = new Set(selected);
    container.replaceChildren();
    const activePlayers = players.filter((player) => player.role === "player" && player.is_active);
    if (!activePlayers.length) {
      const empty = document.createElement("span");
      empty.className = "meta";
      empty.textContent = "Crie contas de jogador antes de associá-las.";
      container.append(empty);
      return;
    }
    for (const player of activePlayers) {
      const label = document.createElement("label");
      label.className = "checkbox member-option";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.value = player.id;
      checkbox.checked = chosen.has(player.id);
      label.append(checkbox, document.createTextNode(player.username));
      container.append(label);
    }
  }

  function selectedMembers(container) {
    return Array.from(container.querySelectorAll('input[type="checkbox"]:checked'), (item) => item.value);
  }

  function campaignStat(label, value) {
    const stat = document.createElement("div");
    stat.className = "campaign-stat";
    const caption = document.createElement("span");
    caption.textContent = label;
    const content = document.createElement("strong");
    content.textContent = value;
    stat.append(caption, content);
    return stat;
  }

  function openMembersDialog(campaign) {
    currentCampaign = campaign;
    membersTitle.textContent = campaign.name;
    membersError.hidden = true;
    memberOptions(editMembers, campaign.members.map((member) => member.id));
    showDialog(membersDialog);
  }

  function openSettingsDialog(campaign) {
    currentCampaign = campaign;
    settingsTitle.textContent = campaign.name;
    settingsError.hidden = true;
    settingsForm.elements.name.value = campaign.name;
    settingsForm.elements.starting_level.value = String(campaign.starting_level);
    settingsForm.elements.max_characters_per_player.value = String(campaign.max_characters_per_player);
    showDialog(settingsDialog);
  }

  function openLifecycleDialog(campaign, action) {
    currentCampaign = campaign;
    lifecycleAction = action;
    lifecycleError.hidden = true;
    if (action === "start") {
      lifecycleTitle.textContent = `Iniciar ${campaign.name}`;
      lifecycleDescription.textContent = `Confirme o início da primeira sessão. O nível inicial ${campaign.starting_level} e o limite de personagens serão bloqueados.`;
      lifecycleConfirm.textContent = "iniciar primeira sessão";
    } else {
      lifecycleTitle.textContent = `Concluir ${campaign.name}`;
      lifecycleDescription.textContent = "Confirme que a campanha foi concluída. As versões dos personagens serão preservadas.";
      lifecycleConfirm.textContent = "concluir campanha";
    }
    showDialog(lifecycleDialog);
  }

  async function openRosterDialog(campaign) {
    rosterTitle.textContent = campaign.name;
    rosterList.textContent = "Carregando personagens…";
    showDialog(rosterDialog);
    const response = await request(`/api/admin/campaigns/${campaign.id}/roster`);
    if (!response.ok) {
      rosterList.textContent = "Não foi possível carregar os personagens.";
      return;
    }
    const roster = await response.json();
    rosterList.replaceChildren();
    for (const member of roster.members) {
      const group = document.createElement("section");
      group.className = "roster-member";
      const heading = document.createElement("h3");
      heading.textContent = member.username;
      group.append(heading);
      if (!member.characters.length) {
        const empty = document.createElement("p");
        empty.className = "meta";
        empty.textContent = "Nenhum personagem nesta campanha.";
        group.append(empty);
      }
      for (const character of member.characters) {
        const row = document.createElement("div");
        row.className = "roster-character";
        const summary = document.createElement("div");
        const name = document.createElement("strong");
        name.textContent = character.identity.name;
        const meta = document.createElement("div");
        meta.className = "meta";
        meta.textContent = `nível ${character.level} · ${statusLabels[character.status]}`;
        summary.append(name, meta);
        const actions = document.createElement("div");
        actions.className = "actions";
        if (character.status === "dead") {
          actions.append(actionButton("reverter morte", async () => {
            const changed = await request(`/api/admin/characters/${character.id}/restore`, { method: "POST" });
            if (changed.ok) await openRosterDialog(campaign);
          }));
        } else if (character.status === "draft" || character.status === "active") {
          actions.append(actionButton("marcar morto", async () => {
            const changed = await request(`/api/admin/characters/${character.id}/mark-dead`, { method: "POST" });
            if (changed.ok) await openRosterDialog(campaign);
          }, "danger-ghost"));
        }
        row.append(summary, actions);
        group.append(row);
      }
      rosterList.append(group);
    }
  }

  async function loadCampaigns() {
    const response = await request("/api/admin/campaigns");
    if (!response.ok) throw new Error("Não foi possível carregar as campanhas.");
    const campaigns = await response.json();
    list.replaceChildren();
    if (!campaigns.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "Nenhuma campanha criada.";
      list.append(empty);
      return;
    }
    for (const campaign of campaigns) {
      const card = document.createElement("article");
      card.className = `campaign-card${campaign.is_active ? " active" : ""}`;
      const heading = document.createElement("div");
      heading.className = "campaign-heading";
      const title = document.createElement("strong");
      title.textContent = campaign.name;
      const badges = document.createElement("div");
      badges.className = "status-badges";
      const contextBadge = document.createElement("span");
      contextBadge.className = campaign.is_active ? "campaign-status active" : "campaign-status";
      contextBadge.textContent = campaign.is_active ? "selecionada" : "não selecionada";
      const lifecycleBadge = document.createElement("span");
      lifecycleBadge.className = `campaign-status lifecycle-${campaign.lifecycle}`;
      lifecycleBadge.textContent = lifecycleLabels[campaign.lifecycle];
      badges.append(contextBadge, lifecycleBadge);
      heading.append(title, badges);

      const summary = document.createElement("div");
      summary.className = "campaign-summary";
      summary.append(
        campaignStat("Regras", `${campaign.rule_pack.name} · v${campaign.rule_pack.version}`),
        campaignStat("Entrada", `nível ${campaign.starting_level} · até ${campaign.max_characters_per_player} por jogador`),
        campaignStat("Membros", campaign.members.length ? campaign.members.map((member) => member.username).join(", ") : "nenhum jogador associado"),
      );

      const actions = document.createElement("div");
      actions.className = "actions";
      actions.append(
        actionButton("personagens", () => openRosterDialog(campaign)),
        actionButton("gerenciar membros", () => openMembersDialog(campaign)),
      );
      if (campaign.lifecycle === "planning") {
        actions.append(
          actionButton("configurar", () => openSettingsDialog(campaign)),
          actionButton("iniciar primeira sessão", () => openLifecycleDialog(campaign, "start"), "primary"),
        );
      } else if (campaign.lifecycle === "in_progress") {
        actions.append(actionButton("concluir campanha", () => openLifecycleDialog(campaign, "complete")));
      }
      if (!campaign.is_active) {
        actions.append(actionButton("selecionar", async () => {
          const changed = await request(`/api/admin/campaigns/${campaign.id}/activate`, { method: "POST" });
          if (!changed.ok) {
            list.textContent = "Não foi possível selecionar a campanha.";
            return;
          }
          await loadCampaigns();
        }));
      }
      card.append(heading, summary, actions);
      list.append(card);
    }
  }

  async function initialize() {
    const [packsResponse, usersResponse] = await Promise.all([
      request("/api/admin/campaigns/rule-packs"),
      request("/api/admin/users"),
    ]);
    if (!packsResponse.ok || !usersResponse.ok) throw new Error("Não foi possível preparar a tela.");
    const packs = await packsResponse.json();
    players = await usersResponse.json();
    packSelect.replaceChildren();
    for (const pack of packs) {
      const option = document.createElement("option");
      option.value = pack.id;
      option.textContent = `${pack.name} · v${pack.version}`;
      packSelect.append(option);
    }
    memberOptions(createMembers);
    openCreateButton.disabled = false;
    await loadCampaigns();
  }

  openCreateButton.addEventListener("click", () => {
    error.hidden = true;
    memberOptions(createMembers);
    showDialog(createDialog);
  });

  for (const dialog of [createDialog, membersDialog, settingsDialog, lifecycleDialog, rosterDialog]) {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) closeDialog(dialog);
    });
    for (const button of dialog.querySelectorAll("[data-close-dialog]")) {
      button.addEventListener("click", () => closeDialog(dialog));
    }
  }

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.hidden = true;
    const data = new FormData(form);
    const response = await request("/api/admin/campaigns", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: data.get("name"),
        rule_pack_id: data.get("rule_pack_id"),
        starting_level: Number(data.get("starting_level")),
        max_characters_per_player: Number(data.get("max_characters_per_player")),
        member_ids: selectedMembers(createMembers),
        activate: data.get("activate") === "on",
      }),
    });
    if (!response.ok) {
      error.textContent = "Não foi possível criar a campanha.";
      error.hidden = false;
      return;
    }
    form.reset();
    form.elements.starting_level.value = "1";
    form.elements.max_characters_per_player.value = "3";
    form.elements.activate.checked = true;
    closeDialog(createDialog);
    await loadCampaigns();
  });

  membersForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    membersError.hidden = true;
    if (!currentCampaign) return;
    const response = await request(`/api/admin/campaigns/${currentCampaign.id}/members`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ member_ids: selectedMembers(editMembers) }),
    });
    if (!response.ok) {
      membersError.textContent = "Não foi possível salvar os membros.";
      membersError.hidden = false;
      return;
    }
    closeDialog(membersDialog);
    await loadCampaigns();
  });

  settingsForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    settingsError.hidden = true;
    if (!currentCampaign) return;
    const data = new FormData(settingsForm);
    const response = await request(`/api/admin/campaigns/${currentCampaign.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        name: data.get("name"),
        starting_level: Number(data.get("starting_level")),
        max_characters_per_player: Number(data.get("max_characters_per_player")),
      }),
    });
    if (!response.ok) {
      settingsError.textContent = "Não foi possível salvar. As configurações podem já estar bloqueadas.";
      settingsError.hidden = false;
      return;
    }
    closeDialog(settingsDialog);
    await loadCampaigns();
  });

  lifecycleForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    lifecycleError.hidden = true;
    if (!currentCampaign || !lifecycleAction) return;
    const response = await request(`/api/admin/campaigns/${currentCampaign.id}/${lifecycleAction}`, { method: "POST" });
    if (!response.ok) {
      lifecycleError.textContent = "Não foi possível alterar o ciclo da campanha.";
      lifecycleError.hidden = false;
      return;
    }
    closeDialog(lifecycleDialog);
    await loadCampaigns();
  });

  initialize().catch((reason) => {
    list.textContent = reason.message || "Não foi possível carregar as campanhas.";
  });
})();
