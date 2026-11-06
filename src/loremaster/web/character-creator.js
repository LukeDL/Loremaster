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

  function render() {
    grid.replaceChildren();
    const usedStandard = Object.values(scores).filter((value) => value !== null);
    for (const [name, labelText] of abilities) {
      const row = document.createElement("label");
      row.className = "ability-row";
      const label = document.createElement("span");
      label.className = "ability-name";
      label.textContent = labelText;
      const select = document.createElement("select");
      select.name = name;
      select.disabled = method === null;
      select.setAttribute("aria-label", labelText);
      const empty = document.createElement("option");
      empty.value = "";
      empty.textContent = "—";
      select.append(empty);
      const values = method === "standard_array" ? standardArray : Object.keys(pointCosts).map(Number);
      const currentCost = scores[name] === null ? 0 : pointCosts[scores[name]];
      for (const value of values) {
        const option = document.createElement("option");
        option.value = String(value);
        option.textContent = method === "point_buy" ? `${value} · ${pointCosts[value]} pt` : String(value);
        option.selected = scores[name] === value;
        if (method === "standard_array" && scores[name] !== value && usedStandard.includes(value)) {
          option.disabled = true;
        }
        if (method === "point_buy" && scores[name] !== value && pointsSpent() - currentCost + pointCosts[value] > 27) {
          option.disabled = true;
        }
        select.append(option);
      }
      select.addEventListener("change", () => {
        scores[name] = select.value === "" ? null : Number(select.value);
        persistedStatus = assignedCount() ? "in_progress" : "not_started";
        render();
      });
      const mod = document.createElement("output");
      mod.className = "ability-modifier";
      mod.textContent = modifier(scores[name]);
      row.append(label, select, mod);
      grid.append(row);
    }

    const assigned = assignedCount();
    summaryAssigned.textContent = `${assigned} de 6`;
    summaryMethod.textContent = method === "standard_array" ? "array padrão" : method === "point_buy" ? "compra por pontos" : "não escolhido";
    summaryStatus.textContent = statusLabel(persistedStatus);
    stepStatus.textContent = statusLabel(persistedStatus);
    if (method === "standard_array") {
      budget.textContent = `${standardArray.length - assigned} valores restantes`;
    } else if (method === "point_buy") {
      const remaining = 27 - pointsSpent();
      budget.textContent = `${remaining} de 27 pontos restantes`;
      budget.classList.toggle("invalid", remaining < 0);
    } else {
      budget.textContent = "Escolha um método";
    }
    saveExit.disabled = method === null;
    completeButton.disabled = method === null || assigned !== 6 || (method === "point_buy" && pointsSpent() > 27);
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
      if (method !== next) scores = Object.fromEntries(abilities.map(([name]) => [name, null]));
      method = next;
      persistedStatus = "not_started";
      showNotice("Método alterado. Distribua os seis valores e salve para registrar a escolha.");
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
