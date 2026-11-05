(() => {
  const form = document.querySelector("#create-campaign");
  const error = document.querySelector("#create-campaign-error");
  const packSelect = form.elements.rule_pack_id;
  const createMembers = document.querySelector("#create-members");
  const list = document.querySelector("#campaigns-list");
  let players = [];

  async function request(url, options = {}) {
    const response = await fetch(url, options);
    if (response.status === 403) throw new Error("Acesso exclusivo do Mestre.");
    return response;
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
      label.className = "checkbox";
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

  function actionButton(label, action, className = "") {
    const element = document.createElement("button");
    element.type = "button";
    element.textContent = label;
    element.className = className;
    element.addEventListener("click", action);
    return element;
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
      const badge = document.createElement("span");
      badge.className = campaign.is_active ? "campaign-status active" : "campaign-status";
      badge.textContent = campaign.is_active ? "ativa" : "inativa";
      heading.append(title, badge);

      const meta = document.createElement("div");
      meta.className = "meta";
      meta.textContent = `${campaign.rule_pack.name} · versão ${campaign.rule_pack.version} · até ${campaign.max_characters_per_player} personagens por jogador`;

      const members = document.createElement("div");
      members.className = "member-options campaign-members";
      memberOptions(members, campaign.members.map((member) => member.id));

      const actions = document.createElement("div");
      actions.className = "actions";
      actions.append(actionButton("salvar jogadores", async () => {
        const response = await request(`/api/admin/campaigns/${campaign.id}/members`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ member_ids: selectedMembers(members) }),
        });
        if (!response.ok) return alert("Não foi possível salvar os jogadores.");
        await loadCampaigns();
      }));
      if (!campaign.is_active) {
        actions.append(actionButton("tornar ativa", async () => {
          const response = await request(`/api/admin/campaigns/${campaign.id}/activate`, { method: "POST" });
          if (!response.ok) return alert("Não foi possível ativar a campanha.");
          await loadCampaigns();
        }, "primary"));
      }

      card.append(heading, meta, members, actions);
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
    await loadCampaigns();
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
    form.elements.max_characters_per_player.value = "3";
    form.elements.activate.checked = true;
    memberOptions(createMembers);
    await loadCampaigns();
  });

  initialize().catch((reason) => {
    list.textContent = reason.message || "Não foi possível carregar as campanhas.";
  });
})();
