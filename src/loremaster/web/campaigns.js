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
  const importReviewDialog = document.querySelector("#import-review-dialog");
  const importReviewForm = document.querySelector("#import-review-form");
  const importReviewTitle = document.querySelector("#import-review-title");
  const importReviewContent = document.querySelector("#import-review-content");
  const importReviewError = document.querySelector("#import-review-error");
  const requestImportChanges = document.querySelector("#request-import-changes");
  const openCreateButton = document.querySelector("#open-create-campaign");
  let players = [];
  let currentCampaign = null;
  let lifecycleAction = null;
  let reviewCharacter = null;
  let reviewRequest = 0;
  let reviewSnapshot = null;

  const lifecycleLabels = {
    planning: "planejamento",
    in_progress: "em andamento",
    completed: "concluída",
  };
  const statusLabels = { draft: "rascunho", active: "ativo", dead: "morto", retired: "retirado" };
  const creationLabels = { not_started: "não iniciados", in_progress: "em andamento", complete: "concluídos" };
  const reviewLabels = { draft: "rascunho", pending: "aguardando revisão", approved: "aprovada", changes_requested: "correção solicitada" };

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

  function reviewFact(label, value) {
    const row = document.createElement("div");
    const term = document.createElement("dt");
    term.textContent = label;
    const detail = document.createElement("dd");
    detail.textContent = value;
    row.append(term, detail);
    return row;
  }

  async function openImportReview(character) {
    const requestId = ++reviewRequest;
    reviewCharacter = character;
    reviewSnapshot = null;
    importReviewError.hidden = true;
    importReviewForm.reset();
    importReviewTitle.textContent = `${character.identity.name} · nível ${character.level}`;
    importReviewContent.textContent = "Carregando snapshot…";
    closeDialog(rosterDialog);
    showDialog(importReviewDialog);
    const response = await request(`/api/admin/characters/${character.id}/import`);
    if (requestId !== reviewRequest || reviewCharacter?.id !== character.id) return;
    if (!response.ok) {
      importReviewContent.textContent = "Não foi possível carregar a reconstrução.";
      return;
    }
    const state = await response.json();
    reviewSnapshot = {
      revision: state.revision,
      hash: state.submitted_snapshot_hash,
    };
    const sheet = document.createElement("dl");
    sheet.className = "review-facts";
    const classes = character.class_progress.classes
      .map((entry) => `${entry.definition.name} ${entry.levels}${entry.is_starting_class ? " (inicial)" : ""}`)
      .join(" · ");
    sheet.append(
      reviewFact("Estado", reviewLabels[state.review_state]),
      reviewFact("Classes", classes || "não informadas"),
      reviewFact("Atributos", state.scores ? `FOR ${state.scores.strength} · DES ${state.scores.dexterity} · CON ${state.scores.constitution} · INT ${state.scores.intelligence} · SAB ${state.scores.wisdom} · CAR ${state.scores.charisma}` : "não informados"),
      reviewFact("HP", state.hit_points.maximum_hp === null ? "não informado" : `${state.hit_points.current_hp}/${state.hit_points.maximum_hp} · ${state.hit_points.temporary_hp} temporário`),
      reviewFact("Procedência", state.attestation || "não informada"),
      reviewFact("Revisão", `snapshot ${state.revision}`),
    );
    importReviewContent.replaceChildren(sheet);
    const pending = state.review_state === "pending";
    importReviewForm.elements.note.disabled = !pending;
    requestImportChanges.disabled = !pending;
    document.querySelector("#approve-import").disabled = !pending;
  }

  async function sendImportReview(decision) {
    if (!reviewCharacter || !reviewSnapshot) return;
    importReviewError.hidden = true;
    const note = importReviewForm.elements.note.value;
    if (decision === "changes_requested" && !note.trim()) {
      importReviewError.textContent = "Explique ao jogador o que precisa ser corrigido.";
      importReviewError.hidden = false;
      return;
    }
    const response = await request(`/api/admin/characters/${reviewCharacter.id}/import/review`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decision,
        note,
        expected_revision: reviewSnapshot.revision,
        expected_snapshot_hash: reviewSnapshot.hash,
      }),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      importReviewError.textContent = body.detail || "Não foi possível registrar a revisão.";
      importReviewError.hidden = false;
      return;
    }
    closeDialog(importReviewDialog);
    if (currentCampaign) await openRosterDialog(currentCampaign);
  }

  async function openRosterDialog(campaign) {
    currentCampaign = campaign;
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
        const progress = character.ability_score_progress;
        const assigned = progress.status === "in_progress" ? ` (${progress.assigned_count}/6)` : "";
        meta.textContent = character.creation_mode === "manual_import"
          ? `nível ${character.level} · ${statusLabels[character.status]} · importação ${reviewLabels[character.import_review_state]}`
          : `nível ${character.level} · ${statusLabels[character.status]} · classe ${creationLabels[character.class_progress.status]} · atributos ${creationLabels[progress.status]}${assigned}`;
        summary.append(name, meta);
        const actions = document.createElement("div");
        actions.className = "actions";
        if (character.creation_mode === "manual_import") {
          actions.append(actionButton(
            character.import_review_state === "pending" ? "revisar importação" : "ver importação",
            () => openImportReview(character),
            character.import_review_state === "pending" ? "primary" : "",
          ));
        }
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

  for (const dialog of [createDialog, membersDialog, settingsDialog, lifecycleDialog, rosterDialog, importReviewDialog]) {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) closeDialog(dialog);
    });
    for (const button of dialog.querySelectorAll("[data-close-dialog]")) {
      button.addEventListener("click", () => closeDialog(dialog));
    }
  }

  importReviewForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    await sendImportReview("approved");
  });
  requestImportChanges.addEventListener("click", () => sendImportReview("changes_requested"));

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
