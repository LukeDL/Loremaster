(() => {
  const match = window.location.pathname.match(/^\/player\/characters\/([^/]+)\/creator\/?$/);
  const versionId = match ? decodeURIComponent(match[1]) : null;
  const endpoint = versionId ? `/api/player/characters/${encodeURIComponent(versionId)}/creator/ability-scores` : null;
  const form = document.querySelector("#ability-form");
  const grid = document.querySelector("#ability-grid");
  const notice = document.querySelector("#creator-notice");
  const error = document.querySelector("#creator-error");
  const budget = document.querySelector("#budget-summary");
  const saveExit = document.querySelector("#save-exit");
  const completeButton = document.querySelector("#complete-step");
  const stepStatus = document.querySelector("#step-status");
  const summaryMethod = document.querySelector("#summary-method");
  const summaryAssigned = document.querySelector("#summary-assigned");
  const summaryStatus = document.querySelector("#summary-status");

  const abilities = [
    ["strength", "Força"],
    ["dexterity", "Destreza"],
    ["constitution", "Constituição"],
    ["intelligence", "Inteligência"],
    ["wisdom", "Sabedoria"],
    ["charisma", "Carisma"],
  ];
  const standardArray = [15, 14, 13, 12, 10, 8];
  const pointCosts = { 8: 0, 9: 1, 10: 2, 11: 3, 12: 4, 13: 5, 14: 7, 15: 9 };
  let method = null;
  let scores = Object.fromEntries(abilities.map(([name]) => [name, null]));
  let persistedStatus = "not_started";

  function modifier(score) {
    if (score === null) return "—";
    const value = Math.floor((score - 10) / 2);
    return value >= 0 ? `+${value}` : String(value);
  }

  function statusLabel(status) {
    return { not_started: "não iniciada", in_progress: "em andamento", complete: "concluída" }[status] || status;
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
    render();
  }

  function render() {
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
    summaryStatus.textContent = statusLabel(persistedStatus);
    stepStatus.textContent = statusLabel(persistedStatus);
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

  function payload() {
    return { method, scores };
  }

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

  async function save() {
    if (!endpoint || !method) return null;
    error.hidden = true;
    const response = await fetch(endpoint, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload()),
    });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      showError(body.detail || "Não foi possível salvar os atributos.");
      return null;
    }
    const state = await response.json();
    persistedStatus = state.status;
    render();
    return state;
  }

  for (const radio of form.elements.method) {
    radio.addEventListener("change", () => {
      const next = form.elements.method.value;
      if (method === next) return;
      method = next;
      if (method === "point_buy") {
        scores = Object.fromEntries(abilities.map(([name]) => [name, scores[name] === null ? 8 : scores[name]]));
      }
      persistedStatus = assignedCount() ? "in_progress" : "not_started";
      showNotice("Método alterado sem apagar os valores. Revise a distribuição antes de salvar.");
      render();
    });
  }

  saveExit.addEventListener("click", async () => {
    if (await save()) window.location.assign("/player");
  });

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!(await save())) return;
    const response = await fetch(`${endpoint}/complete`, { method: "POST" });
    if (!response.ok) {
      const body = await response.json().catch(() => ({}));
      showError(body.detail || "Os atributos ainda não podem ser concluídos.");
      return;
    }
    const state = await response.json();
    persistedStatus = state.status;
    showNotice("Atributos concluídos. O personagem já pode ser ativado.");
    render();
  });

  async function load() {
    if (!endpoint) throw new Error("Personagem inválido.");
    const response = await fetch(endpoint);
    if (!response.ok) throw new Error(response.status === 404 ? "Este personagem não está disponível nesta campanha." : "Não foi possível carregar o criador.");
    const state = await response.json();
    method = state.method;
    scores = state.scores;
    if (method === "point_buy") {
      scores = Object.fromEntries(abilities.map(([name]) => [name, scores[name] === null ? 8 : scores[name]]));
    }
    persistedStatus = state.status;
    if (method) form.elements.method.value = method;
    render();
  }

  render();
  load().catch((reason) => {
    showError(reason.message);
    form.hidden = true;
  });
})();
