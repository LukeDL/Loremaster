(() => {
  const match = window.location.pathname.match(/^\/player\/characters\/([^/]+)\/creator\/?$/);
  const versionId = match ? decodeURIComponent(match[1]) : null;
  const baseEndpoint = versionId ? `/api/player/characters/${encodeURIComponent(versionId)}/creator` : null;
  const classEndpoint = baseEndpoint ? `${baseEndpoint}/classes` : null;
  const abilityEndpoint = baseEndpoint ? `${baseEndpoint}/ability-scores` : null;
  const importEndpoint = baseEndpoint ? `${baseEndpoint}/import` : null;

  const notice = document.querySelector("#creator-notice");
  const error = document.querySelector("#creator-error");
  const classPanel = document.querySelector("#class-panel");
  const abilityPanel = document.querySelector("#ability-panel");
  const importPanel = document.querySelector("#import-panel");
  const classForm = document.querySelector("#class-form");
  const classList = document.querySelector("#class-list");
  const addClass = document.querySelector("#add-class");
  const classTotal = document.querySelector("#class-total");
  const classLevelSum = document.querySelector("#class-level-sum");
  const classStepStatus = document.querySelector("#class-step-status");
  const hpSummary = document.querySelector("#hp-summary");
  const abilityForm = document.querySelector("#ability-form");
  const grid = document.querySelector("#ability-grid");
  const budget = document.querySelector("#budget-summary");
  const saveExit = document.querySelector("#save-exit");
  const completeButton = document.querySelector("#complete-step");
  const stepStatus = document.querySelector("#step-status");
  const summaryMethod = document.querySelector("#summary-method");
  const summaryAssigned = document.querySelector("#summary-assigned");
  const summaryStatus = document.querySelector("#summary-status");
  const importForm = document.querySelector("#import-form");
  const importGrid = document.querySelector("#import-ability-grid");
  const submitImport = document.querySelector("#submit-import");
  const reviewTitle = document.querySelector("#import-review-title");
  const reviewMessage = document.querySelector("#import-review-message");

  const abilities = [
    ["strength", "Força"], ["dexterity", "Destreza"], ["constitution", "Constituição"],
    ["intelligence", "Inteligência"], ["wisdom", "Sabedoria"], ["charisma", "Carisma"],
  ];
  const standardArray = [15, 14, 13, 12, 10, 8];
  const pointCosts = { 8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9 };
  const statusLabels = { not_started: "não iniciada", in_progress: "em andamento", complete: "concluída" };
  const reviewLabels = { draft: "Rascunho", pending: "Aguardando revisão", approved: "Aprovada", changes_requested: "Correção solicitada" };

  let character = null;
  let classDefinitions = [];
  let classRows = [];
  let classPersistedStatus = "not_started";
  let method = null;
  let scores = Object.fromEntries(abilities.map(([name]) => [name, null]));
  let persistedStatus = "not_started";
  let importState = null;

  function showError(message) {
    error.textContent = message;
    error.hidden = false;
    notice.hidden = true;
  }

  function showNotice(message) {
    notice.textContent = message;
    notice.hidden = false;
    error.hidden = true;
  }

  async function responseBody(response, fallback) {
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || fallback);
    return body;
  }

  function modifier(score) {
    if (score === null) return "—";
    const value = Math.floor((score - 10) / 2);
    return value >= 0 ? `+${value}` : String(value);
  }

  function showPanel(panel) {
    classPanel.hidden = panel !== "class";
    abilityPanel.hidden = panel !== "ability";
    importPanel.hidden = panel !== "import";
    document.querySelector("#step-class").classList.toggle("active", panel === "class");
    document.querySelector("#step-abilities").classList.toggle("active", panel !== "class");
  }

  function classDefinition(key) {
    return classDefinitions.find((entry) => entry.key === key);
  }

  function classSum() {
    return classRows.reduce((total, row) => total + Number(row.levels || 0), 0);
  }

  function addClassRow(row = null) {
    const used = new Set(classRows.map((entry) => entry.class_key));
    const fallback = classDefinitions.find((entry) => !used.has(entry.key)) || classDefinitions[0];
    classRows.push(row || {
      class_key: fallback ? fallback.key : "",
      levels: character && character.creation_mode === "new_character" ? character.level : 1,
      is_starting_class: classRows.length === 0,
    });
    classPersistedStatus = "in_progress";
    renderClasses();
  }

  function renderClasses() {
    classList.replaceChildren();
    classRows.forEach((entry, index) => {
      const definition = classDefinition(entry.class_key);
      const row = document.createElement("div");
      row.className = "class-level-row";
      const classField = document.createElement("label");
      classField.textContent = "Classe";
      const select = document.createElement("select");
      select.setAttribute("aria-label", `Classe ${index + 1}`);
      for (const optionDefinition of classDefinitions) {
        const option = document.createElement("option");
        option.value = optionDefinition.key;
        option.textContent = `${optionDefinition.name} · d${optionDefinition.hit_die}`;
        option.selected = entry.class_key === optionDefinition.key;
        option.disabled = classRows.some((item, itemIndex) => itemIndex !== index && item.class_key === optionDefinition.key);
        select.append(option);
      }
      select.addEventListener("change", () => {
        entry.class_key = select.value;
        classPersistedStatus = "in_progress";
        renderClasses();
      });
      classField.append(select);

      const levelField = document.createElement("label");
      levelField.textContent = "Níveis";
      const level = document.createElement("input");
      level.type = "number";
      level.min = "1";
      level.max = "20";
      level.value = String(entry.levels);
      level.disabled = character.creation_mode === "new_character";
      level.addEventListener("input", () => {
        entry.levels = Number(level.value);
        classPersistedStatus = "in_progress";
        updateClassSummary();
      });
      levelField.append(level);

      const starting = document.createElement("label");
      starting.className = "checkbox class-starting";
      const radio = document.createElement("input");
      radio.type = "radio";
      radio.name = "starting_class";
      radio.checked = entry.is_starting_class;
      radio.addEventListener("change", () => {
        classRows.forEach((item, itemIndex) => { item.is_starting_class = itemIndex === index; });
        classPersistedStatus = "in_progress";
      });
      starting.append(radio, document.createTextNode(" classe inicial"));

      const facts = document.createElement("div");
      facts.className = "class-facts meta";
      facts.textContent = definition
        ? `Dado de Vida d${definition.hit_die} · valor fixo ${definition.fixed_hp_per_level} por nível posterior`
        : "";
      row.append(classField, levelField, starting, facts);
      if (character.creation_mode === "manual_import" && classRows.length > 1) {
        const remove = document.createElement("button");
        remove.type = "button";
        remove.textContent = "remover";
        remove.addEventListener("click", () => {
          const wasStarting = classRows[index].is_starting_class;
          classRows.splice(index, 1);
          if (wasStarting && classRows.length) classRows[0].is_starting_class = true;
          classPersistedStatus = "in_progress";
          renderClasses();
        });
        row.append(remove);
      }
      classList.append(row);
    });
    addClass.hidden = !character || character.creation_mode !== "manual_import" || classRows.length >= classDefinitions.length;
    updateClassSummary();
  }

  function updateClassSummary() {
    const total = classSum();
    classTotal.textContent = `${total} de ${character ? character.level : "—"} níveis informados`;
    classTotal.classList.toggle("invalid", Boolean(character) && total !== character.level);
    classLevelSum.textContent = String(total);
    classStepStatus.textContent = statusLabels[classPersistedStatus] || classPersistedStatus;
  }

  function assignedCount() {
    return Object.values(scores).filter((value) => value !== null).length;
  }

  function pointsSpent() {
    return Object.values(scores).reduce((total, value) => total + (value === null ? 0 : pointCosts[value]), 0);
  }

  function standardArrayIsValid() {
    const assigned = Object.values(scores).filter((value) => value !== null).sort((a, b) => b - a);
    return assigned.length === standardArray.length && assigned.every((value, index) => value === standardArray[index]);
  }

  function updateScore(name, value) {
    scores[name] = value;
    persistedStatus = assignedCount() ? "in_progress" : "not_started";
    renderAbilities();
  }

  function renderAbilities() {
    grid.replaceChildren();
    const usedStandard = Object.values(scores).filter((value) => value !== null);
    for (const [name, labelText] of abilities) {
      const row = document.createElement("div");
      row.className = "ability-row";
      const label = document.createElement("span");
      label.className = "ability-name";
      label.textContent = labelText;
      const mod = document.createElement("output");
      mod.className = "ability-modifier";
      mod.setAttribute("aria-label", `Modificador de ${labelText}`);
      mod.textContent = modifier(scores[name]);
      if (method === "point_buy") {
        row.classList.add("point-buy-row");
        const controls = document.createElement("div");
        controls.className = "score-stepper";
        const decrease = document.createElement("button");
        decrease.type = "button";
        decrease.className = "score-stepper-button";
        decrease.textContent = "−";
        decrease.setAttribute("aria-label", `Diminuir ${labelText}`);
        decrease.disabled = scores[name] === null || scores[name] <= 8;
        decrease.addEventListener("click", () => updateScore(name, scores[name] - 1));
        const value = document.createElement("output");
        value.className = "ability-value";
        value.setAttribute("aria-label", `Valor de ${labelText}`);
        value.textContent = scores[name] === null ? "—" : String(scores[name]);
        const increase = document.createElement("button");
        increase.type = "button";
        increase.className = "score-stepper-button";
        increase.textContent = "+";
        increase.setAttribute("aria-label", `Aumentar ${labelText}`);
        const current = scores[name] === null ? 8 : scores[name];
        const nextCost = current < 15 ? pointCosts[current + 1] : null;
        increase.disabled = current >= 15 || pointsSpent() - pointCosts[current] + nextCost > 27;
        increase.addEventListener("click", () => updateScore(name, current + 1));
        controls.append(decrease, value, increase);
        row.append(label, mod, controls);
      } else {
        const select = document.createElement("select");
        select.name = name;
        select.disabled = method === null;
        select.setAttribute("aria-label", labelText);
        const empty = document.createElement("option");
        empty.value = "";
        empty.textContent = "—";
        select.append(empty);
        const current = scores[name];
        const values = current !== null && !standardArray.includes(current) ? [current, ...standardArray] : standardArray;
        for (const optionValue of values) {
          const option = document.createElement("option");
          option.value = String(optionValue);
          option.textContent = standardArray.includes(optionValue) ? String(optionValue) : `${optionValue} · ajuste necessário`;
          option.selected = current === optionValue;
          if (current !== optionValue && usedStandard.includes(optionValue)) option.disabled = true;
          select.append(option);
        }
        const duplicate = current !== null && usedStandard.filter((value) => value === current).length > 1;
        const incompatible = current !== null && (!standardArray.includes(current) || duplicate);
        row.classList.toggle("invalid", incompatible);
        select.setAttribute("aria-invalid", incompatible ? "true" : "false");
        select.addEventListener("change", () => updateScore(name, select.value === "" ? null : Number(select.value)));
        row.append(label, select, mod);
      }
      grid.append(row);
    }
    const assigned = assignedCount();
    summaryAssigned.textContent = `${assigned} de 6`;
    summaryMethod.textContent = method === "standard_array" ? "array padrão" : method === "point_buy" ? "compra por pontos" : "não escolhido";
    summaryStatus.textContent = statusLabels[persistedStatus] || persistedStatus;
    stepStatus.textContent = statusLabels[persistedStatus] || persistedStatus;
    if (method === "standard_array") {
      budget.textContent = standardArrayIsValid() ? "array distribuído" : `${standardArray.length - assigned} valores restantes`;
      if (assigned === 6 && !standardArrayIsValid()) budget.textContent = "ajuste a distribuição ao array padrão";
      budget.classList.toggle("invalid", assigned === 6 && !standardArrayIsValid());
    } else if (method === "point_buy") {
      const remaining = 27 - pointsSpent();
      budget.textContent = `${remaining} de 27 pontos restantes`;
      budget.classList.toggle("invalid", remaining < 0);
    } else {
      budget.textContent = "Escolha um método";
      budget.classList.remove("invalid");
    }
    saveExit.disabled = method === null;
    completeButton.disabled = method === null || assigned !== 6 || (method === "standard_array" && !standardArrayIsValid()) || (method === "point_buy" && pointsSpent() > 27);
  }

  async function saveAbilities() {
    if (!abilityEndpoint || !method) return null;
    const response = await fetch(abilityEndpoint, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ method, scores }),
    });
    const state = await responseBody(response, "Não foi possível salvar os atributos.");
    persistedStatus = state.status;
    renderAbilities();
    return state;
  }

  function renderImportGrid() {
    importGrid.replaceChildren();
    for (const [name, labelText] of abilities) {
      const label = document.createElement("label");
      label.textContent = labelText;
      const input = document.createElement("input");
      input.name = name;
      input.type = "number";
      input.min = "1";
      input.max = "30";
      input.required = true;
      label.append(input);
      importGrid.append(label);
    }
  }

  function lockClassEditor(locked) {
    for (const field of classForm.elements) field.disabled = locked;
  }

  function fillImport(state) {
    importState = state;
    if (state.scores) {
      for (const [name] of abilities) importForm.elements[name].value = state.scores[name];
    }
    const hp = state.hit_points;
    if (hp.maximum_hp !== null) importForm.elements.maximum_hp.value = hp.maximum_hp;
    if (hp.current_hp !== null) importForm.elements.current_hp.value = hp.current_hp;
    if (hp.temporary_hp !== null) importForm.elements.temporary_hp.value = hp.temporary_hp;
    if (state.attestation) importForm.elements.attestation.value = state.attestation;
    reviewTitle.textContent = reviewLabels[state.review_state] || state.review_state;
    reviewMessage.textContent = state.review_state === "pending"
      ? "O snapshot enviado está bloqueado enquanto o Mestre revisa."
      : state.review_state === "approved"
        ? "O Mestre aprovou este snapshot. O personagem pode ser ativado na página de personagens."
        : state.review_state === "changes_requested"
          ? state.review_note || "O Mestre solicitou correções."
          : "Salve a transcrição e envie ao Mestre quando estiver completa.";
    const locked = state.review_state === "pending" || state.review_state === "approved";
    for (const field of importForm.elements) field.disabled = locked;
    lockClassEditor(locked);
    submitImport.disabled = locked;
  }

  async function saveImportData() {
    const scoresPayload = Object.fromEntries(abilities.map(([name]) => [name, Number(importForm.elements[name].value)]));
    const payload = {
      scores: scoresPayload,
      maximum_hp: Number(importForm.elements.maximum_hp.value),
      current_hp: Number(importForm.elements.current_hp.value),
      temporary_hp: Number(importForm.elements.temporary_hp.value),
      attestation: importForm.elements.attestation.value,
    };
    const response = await fetch(importEndpoint, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const state = await responseBody(response, "Não foi possível salvar a reconstrução.");
    fillImport(state);
    return state;
  }

  document.querySelector("#step-class").addEventListener("click", () => showPanel("class"));
  document.querySelector("#step-abilities").addEventListener("click", () => showPanel(character && character.creation_mode === "manual_import" ? "import" : "ability"));
  addClass.addEventListener("click", () => addClassRow());

  classForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      const response = await fetch(classEndpoint, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ classes: classRows }),
      });
      const state = await responseBody(response, "Não foi possível salvar as classes.");
      classRows = state.classes.map(({ class_key, levels, is_starting_class }) => ({ class_key, levels, is_starting_class }));
      classPersistedStatus = state.status;
      renderClasses();
      showNotice("Classe e níveis salvos.");
      showPanel(character.creation_mode === "manual_import" ? "import" : "ability");
    } catch (reason) {
      showError(reason.message);
    }
  });

  for (const radio of abilityForm.elements.method) {
    radio.addEventListener("change", () => {
      const next = abilityForm.elements.method.value;
      if (method === next) return;
      method = next;
      if (method === "point_buy") scores = Object.fromEntries(abilities.map(([name]) => [name, scores[name] === null ? 8 : scores[name]]));
      persistedStatus = assignedCount() ? "in_progress" : "not_started";
      showNotice("Método alterado sem apagar os valores. Revise a distribuição antes de salvar.");
      renderAbilities();
    });
  }

  saveExit.addEventListener("click", async () => {
    try {
      if (await saveAbilities()) window.location.assign("/player");
    } catch (reason) {
      showError(reason.message);
    }
  });

  abilityForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      if (!(await saveAbilities())) return;
      const response = await fetch(`${abilityEndpoint}/complete`, { method: "POST" });
      const state = await responseBody(response, "Os atributos ainda não podem ser concluídos.");
      persistedStatus = state.status;
      renderAbilities();
      const characters = await responseBody(await fetch("/api/player/characters"), "Não foi possível atualizar o HP.");
      character = characters.find((entry) => entry.id === versionId) || character;
      hpSummary.textContent = character.hit_point_progress.maximum_hp === null
        ? "aguardando classe e Constituição"
        : `${character.hit_point_progress.maximum_hp} máximo · ${character.hit_point_progress.source === "level_one_formula" ? "fórmula de nível 1" : "progressão fixa"}`;
      showNotice("Classe, atributos e HP concluídos. As etapas futuras ainda não fazem parte deste incremento.");
    } catch (reason) {
      showError(reason.message);
    }
  });

  importForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await saveImportData();
      showNotice("Reconstrução salva como rascunho.");
    } catch (reason) {
      showError(reason.message);
    }
  });

  submitImport.addEventListener("click", async () => {
    try {
      await saveImportData();
      const response = await fetch(`${importEndpoint}/submit`, { method: "POST" });
      const state = await responseBody(response, "Não foi possível enviar a reconstrução.");
      fillImport(state);
      showNotice("Snapshot enviado ao Mestre para revisão.");
    } catch (reason) {
      showError(reason.message);
    }
  });

  async function load() {
    if (!baseEndpoint) throw new Error("Personagem inválido.");
    renderImportGrid();
    const [charactersResponse, optionsResponse, classesResponse] = await Promise.all([
      fetch("/api/player/characters"),
      fetch("/api/player/rule-options/classes"),
      fetch(classEndpoint),
    ]);
    const characters = await responseBody(charactersResponse, "Não foi possível carregar o personagem.");
    character = characters.find((entry) => entry.id === versionId);
    if (!character) throw new Error("Este personagem não está disponível nesta campanha.");
    classDefinitions = await responseBody(optionsResponse, "Não foi possível carregar as classes.");
    const classState = await responseBody(classesResponse, "Não foi possível carregar as classes do personagem.");
    classRows = classState.classes.map(({ class_key, levels, is_starting_class }) => ({ class_key, levels, is_starting_class }));
    classPersistedStatus = classState.status;
    if (!classRows.length) addClassRow();
    else renderClasses();

    document.querySelector("#creator-title").textContent = character.identity.name;
    document.querySelector("#creator-context").textContent = `${character.campaign.name} · nível ${character.level} · ${character.creation_mode === "manual_import" ? "reconstrução de personagem existente" : "personagem novo"}`;
    document.querySelector("#character-level").textContent = String(character.level);
    hpSummary.textContent = character.hit_point_progress.maximum_hp === null
      ? "aguardando classe e Constituição"
      : `${character.hit_point_progress.maximum_hp} máximo`;
    document.querySelector("#class-guidance").textContent = character.creation_mode === "manual_import"
      ? "Informe todas as classes e níveis atuais. A soma deve corresponder ao nível total; nenhuma multiclasse será descartada."
      : "Escolha a classe do personagem. O dado de vida e as proficiências são definidos pelo pacote SRD 5.2.1.";

    if (character.creation_mode === "manual_import") {
      document.querySelector("#step-status").textContent = reviewLabels[character.import_review_state] || character.import_review_state;
      const state = await responseBody(await fetch(importEndpoint), "Não foi possível carregar a reconstrução.");
      fillImport(state);
    } else {
      const state = await responseBody(await fetch(abilityEndpoint), "Não foi possível carregar os atributos.");
      method = state.method;
      scores = state.scores;
      if (method === "point_buy") scores = Object.fromEntries(abilities.map(([name]) => [name, scores[name] === null ? 8 : scores[name]]));
      persistedStatus = state.status;
      if (method) abilityForm.elements.method.value = method;
      renderAbilities();
    }
    showPanel(classPersistedStatus === "complete" ? (character.creation_mode === "manual_import" ? "import" : "ability") : "class");
  }

  renderAbilities();
  load().catch((reason) => {
    showError(reason.message);
    classPanel.hidden = true;
    abilityPanel.hidden = true;
    importPanel.hidden = true;
  });
})();
