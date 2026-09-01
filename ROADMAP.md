# Loremaster — Roadmap

## Atualizando dependências frontend vendorizadas

O app não usa CDN — todas as libs JS/CSS estão em `src/loremaster/web/vendor/`
pra funcionar em mesas sem internet. Pra atualizar uma versão, baixe
manualmente da fonte oficial e substitua:

```bash
cd src/loremaster/web/vendor
# Vue (bundle IIFE pra /, e ESM pra /map)
curl -sfLo vue.global.prod.js       'https://cdn.jsdelivr.net/npm/vue@<VER>/dist/vue.global.prod.js'
curl -sfLo vue.esm-browser.prod.js  'https://cdn.jsdelivr.net/npm/vue@<VER>/dist/vue.esm-browser.prod.js'
# Vue Flow (core + plugins). Os .mjs oficiais só importam "vue" e
# "@vue-flow/core" (resolvidos pelo import map em map.html).
curl -sfLo vue-flow-core.js         'https://cdn.jsdelivr.net/npm/@vue-flow/core@<VER>/dist/vue-flow-core.mjs'
curl -sfLo vue-flow-background.js   'https://cdn.jsdelivr.net/npm/@vue-flow/background@<VER>/dist/vue-flow-background.mjs'
curl -sfLo vue-flow-controls.js     'https://cdn.jsdelivr.net/npm/@vue-flow/controls@<VER>/dist/vue-flow-controls.mjs'
curl -sfLo vue-flow-minimap.js      'https://cdn.jsdelivr.net/npm/@vue-flow/minimap@<VER>/dist/vue-flow-minimap.mjs'
# CSS
curl -sfLo vue-flow-core.css         'https://cdn.jsdelivr.net/npm/@vue-flow/core@<VER>/dist/style.css'
curl -sfLo vue-flow-theme-default.css 'https://cdn.jsdelivr.net/npm/@vue-flow/core@<VER>/dist/theme-default.css'
curl -sfLo vue-flow-controls.css     'https://cdn.jsdelivr.net/npm/@vue-flow/controls@<VER>/dist/style.css'
curl -sfLo vue-flow-minimap.css      'https://cdn.jsdelivr.net/npm/@vue-flow/minimap@<VER>/dist/style.css'
# wavesurfer.js (usado pelo editor de loop region)
curl -sfLo wavesurfer.esm.js         'https://cdn.jsdelivr.net/npm/wavesurfer.js@<VER>/dist/wavesurfer.esm.js'
curl -sfLo wavesurfer-regions.esm.js 'https://cdn.jsdelivr.net/npm/wavesurfer.js@<VER>/dist/plugins/regions.esm.js'
```

Depois abrir `/` e `/map` no browser, verificar no DevTools > Network que
nenhuma requisição sai pra domínio externo.

## Fora do MVP, planejado

### Editor visual de cenas em node graph (state machine)

**Status**: em desenvolvimento (M7, após M6).

Cada cena vira um nó no canvas; a política `on_end` de cada cena vira uma
aresta que aponta pra outra cena (ou pra `stop`). O mestre "desenha" o fluxo
da campanha e visualiza de bate-pronto o que vai acontecer quando apertar
`FIM DE COMBATE` em qualquer cena. Roda no notebook (mouse-first) — não
substitui a UI atual do tablet, que continua sendo a interface de execução
durante a mesa.

### Módulos plugáveis via event bus

O `EventBus` in-process do MVP já é a fundação. Módulos futuros são funções
que fazem `bus.subscribe(EventType, handler)` no startup:

- **OBS**: subscriber em `ScenePlaybackStarted` troca a cena do OBS via
  `obs-websocket`. Cria as cenas do OBS programaticamente na primeira
  execução se ainda não existirem.
- **Iluminação (Hue, Home Assistant)**: subscriber em `CombatEnded` /
  `ScenePlaybackStarted` dispara comandos MQTT ou REST para dimmar/colorir
  luzes conforme a cena.
- **Ponte MQTT bidirecional**: `mqtt_bridge` republica todo evento do bus
  em um tópico MQTT e consome tópicos externos para republicar como
  eventos locais. Permite integração com qualquer coisa IoT.

Cada módulo é ativado por config (`config.py`). O core não precisa mudar.

## Ideias sob avaliação (backlog)

### Editor de sound design com nós = camadas de uma cena (Skyrim/Wwise-like)

Uma segunda modalidade de edição, complementar ao grafo de cenas: dentro
de UMA cena, cada camada vira um nó (fonte de áudio) e você monta uma
rede de mixing conectando nós de camada → nós de efeito (ganho, filtro,
delay, panner) → nó `output`. Modular synth estilo Wwise / FMOD Studio.

**Motivação**: transformar o Loremaster de "player de camadas simples"
em ferramenta séria de sound design pra RPG. Permitiria efeitos como:

- Ambiente adaptativo: layer de vento com filtro low-pass que abre
  quando a cena "combate" começa (afeta trilha de exploração residual).
- Sidechain: música baixa quando fala do NPC toca por cima.
- Efeitos por camada: reverb só na trilha, delay só nos SFX, EQ na voz.
- Buses: agrupar camadas em "música", "ambiente", "SFX" e controlar
  volume do bus inteiro.

**Custo estimado**: alto. Requer:

- Novo modelo de dados: `Layer` vira um DAG (nós + conexões), não uma
  lista plana.
- Extensão do mixer NumPy: cadeia de efeitos em cada callback, mantendo
  latência baixa. Efeitos comuns (biquad EQ, delay circular, reverb
  simples) implementáveis em NumPy sem lib externa; reverb de qualidade
  provavelmente precisa `pedalboard` ou `scipy.signal`.
- UI: node editor bem mais denso que o grafo de cenas — muitos tipos de
  nó, pinos tipados (áudio vs. controle), ordering topológico.

**Quando fazer**: depois do M7 (grafo de cenas) e depois de a ferramenta
ter sido usada em algumas sessões reais, quando ficar claro quais
efeitos/roteamentos são realmente úteis. Fazer especulativamente antes
de saber o que precisa é receita pra construir features que ninguém usa.

**Compatibilidade**: cenas "simples" (camadas planas do MVP) continuam
suportadas — nova UI é opt-in, cena antiga é interpretada como grafo
trivial (todas as camadas → mixer master → output).

### Multi-usuário / co-mestrar

Autenticação leve, permissões por cena. Só faz sentido em campanhas com
mais de um mestre — provavelmente nunca.

### Ferramentas de sessão adicionais

- Timer de round de combate visível na TV.
- Iniciativa tracker integrado (arrastar fichas de jogadores/inimigos).
- Overlay de imagens/mapas na TV (integração com OBS ou canvas próprio).
- Dice roller sincronizado (mestre rola, mostra na TV).

Nenhuma dessas é essencial — o Loremaster foca em áudio/luz/ambiente.
Se virarem escopo, avaliar antes se não vale integrar ferramentas
existentes (Owlbear Rodeo, Roll20) em vez de reimplementar.
