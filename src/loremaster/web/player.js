(() => {
  const campaignLabel = document.querySelector("#selected-campaign");
  const campaignPicker = document.querySelector("#player-campaign-picker");
  const campaignSelect = document.querySelector("#player-campaign-select");
  const list = document.querySelector("#characters-list");
  const notice = document.querySelector("#player-notice");
  const openCreateButton = document.querySelector("#open-create-character");
  const createDialog = document.querySelector("#create-character-dialog");
  const createForm = document.querySelector("#create-character");
  const createError = document.querySelector("#create-character-error");
  const newNameLabel = document.querySelector("#new-character-name");
  const existingPicker = document.querySelector("#existing-character-picker");
  const manualImportOption = document.querySelector("#manual-import-option");
  const importLevelField = document.querySelector("#import-level-field");
  const entryModeHelp = document.querySelector("#entry-mode-help");
  const identitySelect = createForm.elements.identity_id;
  const renameDialog = document.querySelector("#rename-character-dialog");
  const renameForm = document.querySelector("#rename-character");
  const renameError = document.querySelector("#rename-character-error");
  const statusDialog = document.querySelector("#character-status-dialog");
  const statusForm = document.querySelector("#character-status-form");
  const statusTitle = document.querySelector("#character-status-title");
  const statusDescription = document.querySelector("#character-status-description");
  const statusConfirm = document.querySelector("#character-status-confirm");
  const statusError = document.querySelector("#character-status-error");
  let campaign = null;
  let identities = [];
  let selectedCharacter = null;
  let statusAction = null;
  let noticeTimer = null;

  const lifecycleLabels = { planning: "planejamento", in_progress: "em andamento", completed: "concluída" };
  const statusLabels = { draft: "rascunho", active: "ativo", dead: "morto", retired: "retirado" };
  const creationLabels = { not_started: "não iniciados", in_progress: "em andamento", complete: "concluídos" };
  const reviewLabels = { draft: "rascunho", pending: "aguardando Mestre", approved: "aprovada", changes_requested: "correção solicitada", not_required: "não necessária" };

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

  function button(label, action, className = "") {
    const element = document.createElement("button");
    element.type = "button";
    element.textContent = label;
    element.className = className;
    element.addEventListener("click", action);
    return element;
  }

  function setSourceFields() {
    const source = createForm.elements.source.value;
    const isNew = source === "new";
    newNameLabel.hidden = !isNew;
    existingPicker.hidden = isNew;
    createForm.elements.name.required = isNew;
    identitySelect.required = !isNew;
  }

  function setEntryModeFields() {
    const isImport = createForm.elements.creation_mode.value === "manual_import";
    importLevelField.hidden = !isImport;
    createForm.elements.level.required = isImport;
    entryModeHelp.textContent = isImport
      ? "A reconstrução preserva os valores da ficha atual e exige revisão do Mestre antes da ativação."
      : "A versão nasce no nível inicial da campanha e terá progressão independente.";
  }

  function openRename(character) {
    selectedCharacter = character;
    renameError.hidden = true;
    renameForm.elements.name.value = character.identity.name;
    showDialog(renameDialog);
  }

  function openStatus(character, action) {
    selectedCharacter = character;
    statusAction = action;
    statusError.hidden = true;
    if (action === "activate") {
      statusTitle.textContent = `Ativar ${character.identity.name}`;
      statusDescription.textContent = "Este será seu único personagem ativo na campanha.";
      statusConfirm.textContent = "ativar personagem";
    } else {
      statusTitle.textContent = `Retirar ${character.identity.name}`;
      statusDescription.textContent = "O personagem permanecerá preservado nesta campanha, mas ficará retirado.";
      statusConfirm.textContent = "retirar personagem";
    }
    showDialog(statusDialog);
  }

  function renderCharacters(characters) {
    list.replaceChildren();
    if (!characters.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = "Nenhum personagem nesta campanha. Crie seu primeiro rascunho.";
      list.append(empty);
      return;
    }
    for (const character of characters) {
      const card = document.createElement("article");
      card.className = `campaign-card character-card status-${character.status}`;
      const heading = document.createElement("div");
      heading.className = "campaign-heading";
      const title = document.createElement("strong");
      title.textContent = character.identity.name;
      const badge = document.createElement("span");
      badge.className = `campaign-status character-status-${character.status}`;
      badge.textContent = statusLabels[character.status];
      heading.append(title, badge);
      const summary = document.createElement("div");
      summary.className = "campaign-summary";
      const level = document.createElement("div");
      level.className = "campaign-stat";
      level.innerHTML = `<span>Nível</span><strong>${character.level}</strong>`;
      const rules = document.createElement("div");
      rules.className = "campaign-stat";
      const rulesLabel = document.createElement("span");
      rulesLabel.textContent = "Regras";
      const rulesValue = document.createElement("strong");
      rulesValue.textContent = `${character.campaign.rule_pack.name} · v${character.campaign.rule_pack.version}`;
      rules.append(rulesLabel, rulesValue);
      const creation = document.createElement("div");
      creation.className = "campaign-stat";
      const creationLabel = document.createElement("span");
      creationLabel.textContent = character.creation_mode === "manual_import" ? "Importação" : "Criação";
      const creationValue = document.createElement("strong");
      creationValue.textContent = character.creation_mode === "manual_import"
        ? reviewLabels[character.import_review_state]
        : `classe ${creationLabels[character.class_progress.status]} · atributos ${creationLabels[character.ability_score_progress.status]}`;
      creation.append(creationLabel, creationValue);
      summary.append(level, rules, creation);
      const actions = document.createElement("div");
      actions.className = "actions";
      actions.append(button("renomear identidade", () => openRename(character)));
      if (character.status === "draft") {
        const ready = character.creation_mode === "manual_import"
          ? character.import_review_state === "approved"
          : character.class_progress.status === "complete"
            && character.ability_score_progress.status === "complete"
            && character.hit_point_progress.status === "complete";
        const creatorLabel = character.creation_mode === "manual_import"
          ? character.import_review_state === "draft" ? "preencher reconstrução" : "revisar reconstrução"
          : character.class_progress.status === "not_started" ? "começar criação" : "continuar criação";
        actions.append(button(creatorLabel, () => {
          window.location.assign(`/player/characters/${encodeURIComponent(character.id)}/creator`);
        }, ready ? "" : "primary"));
        if (ready) {
          actions.append(button("ativar", () => openStatus(character, "activate"), "primary"));
        }
      }
      if (character.status === "draft" || character.status === "active") {
        actions.append(button("retirar", () => openStatus(character, "retire")));
      }
      card.append(heading, summary, actions);
      list.append(card);
    }
  }

  async function load() {
    const [campaignsResponse, campaignResponse, identitiesResponse] = await Promise.all([
      fetch("/api/player/campaigns"),
      fetch("/api/player/campaign"),
      fetch("/api/player/character-identities"),
    ]);
    if (!campaignsResponse.ok || !identitiesResponse.ok) {
      throw new Error("Não foi possível carregar suas campanhas.");
    }
    const campaigns = await campaignsResponse.json();
    identities = await identitiesResponse.json();
    campaignSelect.replaceChildren();
    if (campaigns.length > 1) {
      const placeholder = document.createElement("option");
      placeholder.value = "";
      placeholder.textContent = "Escolha uma campanha";
      campaignSelect.append(placeholder);
    }
    for (const available of campaigns) {
      const option = document.createElement("option");
      option.value = available.id;
      option.textContent = available.name;
      campaignSelect.append(option);
    }
    campaignPicker.hidden = campaigns.length < 2;
    if (campaignResponse.status === 404) {
      campaign = null;
      campaignSelect.value = "";
      campaignLabel.textContent = campaigns.length
        ? "Escolha uma das suas campanhas para ver e administrar os personagens."
        : "Você ainda não faz parte de nenhuma campanha.";
      list.innerHTML = '<div class="empty-state">Nenhuma campanha selecionada.</div>';
      openCreateButton.disabled = true;
      return;
    }
    if (!campaignResponse.ok) {
      throw new Error("Não foi possível carregar seus personagens.");
    }
    campaign = await campaignResponse.json();
    campaignSelect.value = campaign.id;
    const charactersResponse = await fetch("/api/player/characters");
    if (!charactersResponse.ok) throw new Error("Não foi possível carregar seus personagens.");
    const characters = await charactersResponse.json();
    campaignLabel.textContent = `${campaign.name} · nível inicial ${campaign.starting_level} · ${lifecycleLabels[campaign.lifecycle]}`;
    renderCharacters(characters);
    openCreateButton.disabled = false;
  }

  campaignSelect.addEventListener("change", async () => {
    if (!campaignSelect.value) return;
    openCreateButton.disabled = true;
    const response = await fetch("/api/player/campaign", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ campaign_id: campaignSelect.value }),
    });
    if (!response.ok) {
      showNotice("Não foi possível selecionar esta campanha.");
      await load();
      return;
    }
    await load();
  });

  openCreateButton.addEventListener("click", () => {
    createForm.reset();
    createError.hidden = true;
    identitySelect.replaceChildren();
    const usedHere = new Set(
      identities.flatMap((identity) => identity.versions)
        .filter((version) => version.campaign.id === campaign.id)
        .map((version) => version.identity.id),
    );
    for (const identity of identities.filter((item) => !usedHere.has(item.id))) {
      const option = document.createElement("option");
      option.value = identity.id;
      option.textContent = identity.name;
      identitySelect.append(option);
    }
    const existingRadio = createForm.querySelector('input[value="existing"]');
    existingRadio.disabled = !identitySelect.options.length;
    const importRadio = createForm.querySelector('input[value="manual_import"]');
    importRadio.disabled = campaign.lifecycle !== "in_progress";
    manualImportOption.classList.toggle("disabled", importRadio.disabled);
    setSourceFields();
    setEntryModeFields();
    showDialog(createDialog);
  });

  for (const radio of createForm.elements.source) radio.addEventListener("change", setSourceFields);
  for (const radio of createForm.elements.creation_mode) radio.addEventListener("change", setEntryModeFields);
  for (const dialog of [createDialog, renameDialog, statusDialog]) {
    dialog.addEventListener("click", (event) => {
      if (event.target === dialog) closeDialog(dialog);
    });
    for (const closeButton of dialog.querySelectorAll("[data-close-dialog]")) {
      closeButton.addEventListener("click", () => closeDialog(dialog));
    }
  }

  createForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    createError.hidden = true;
    const data = new FormData(createForm);
    const payload = data.get("source") === "new"
      ? { name: data.get("name") }
      : { identity_id: data.get("identity_id") };
    payload.creation_mode = data.get("creation_mode");
    if (payload.creation_mode === "manual_import") payload.level = Number(data.get("level"));
    const response = await fetch("/api/player/characters", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      createError.textContent = body.detail || "Não foi possível criar o personagem.";
      createError.hidden = false;
      return;
    }
    const created = await response.json();
    closeDialog(createDialog);
    window.location.assign(`/player/characters/${encodeURIComponent(created.id)}/creator`);
  });

  renameForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    renameError.hidden = true;
    if (!selectedCharacter) return;
    const response = await fetch(`/api/player/character-identities/${selectedCharacter.identity.id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: new FormData(renameForm).get("name") }),
    });
    if (!response.ok) {
      renameError.textContent = "Não foi possível renomear o personagem.";
      renameError.hidden = false;
      return;
    }
    closeDialog(renameDialog);
    showNotice("Identidade atualizada em todas as campanhas.");
    await load();
  });

  statusForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    statusError.hidden = true;
    if (!selectedCharacter || !statusAction) return;
    const response = await fetch(`/api/player/characters/${selectedCharacter.id}/${statusAction}`, { method: "POST" });
    if (!response.ok) {
      statusError.textContent = response.status === 409
        ? "Essa mudança de estado não é permitida ou já existe outro personagem ativo."
        : "Não foi possível alterar o estado.";
      statusError.hidden = false;
      return;
    }
    closeDialog(statusDialog);
    showNotice(statusAction === "activate" ? "Personagem ativado." : "Personagem retirado.");
    await load();
  });

  load().catch((reason) => {
    campaignLabel.textContent = reason.message || "Não foi possível carregar a área do jogador.";
  });
})();
