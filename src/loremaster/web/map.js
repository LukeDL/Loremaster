// Loremaster — campaign map (node graph editor).
// Vue 3 + Vue Flow via import map (see map.html).
// Palette (left) lists every scene; canvas (right) shows only opt-in ones.

import { createApp, ref, computed, onMounted, onBeforeUnmount, watch, defineComponent, h, markRaw, nextTick, reactive, Fragment } from "vue";
import { VueFlow, Handle, Position, useVueFlow, BaseEdge, EdgeLabelRenderer, getSmoothStepPath } from "@vue-flow/core";
import { Background } from "@vue-flow/background";
import { Controls } from "@vue-flow/controls";
import { MiniMap } from "@vue-flow/minimap";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/plugins/regions.esm.js";

// ---- API -------------------------------------------------------------------

const API = {
  async listScenes() { return (await fetch("/api/scenes")).json(); },
  async listUploads() { return (await fetch("/api/uploads")).json(); },
  async createScene(payload) {
    const r = await fetch("/api/scenes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    return r.ok ? r.json() : null;
  },
  async updateScene(id, payload) {
    return fetch(`/api/scenes/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  async deleteScene(id) { return fetch(`/api/scenes/${id}`, { method: "DELETE" }); },
  async setPosition(id, x, y) {
    return fetch(`/api/scenes/${id}/position`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ x, y }),
    });
  },
  async setOnMap(id, is_on_map, position) {
    const body = { is_on_map };
    if (position) { body.x = position.x; body.y = position.y; }
    return fetch(`/api/scenes/${id}/map`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
  },
  async setOnEnd(id, on_end) {
    return fetch(`/api/scenes/${id}/on_end`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ on_end }),
    });
  },
  async setEntryScene(scene_id) {
    return fetch("/api/entry_scene", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene_id }),
    });
  },
  async play(sceneId) {
    return fetch("/api/playback/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene_id: sceneId }),
    });
  },
  async stop() { return fetch("/api/playback/stop", { method: "POST" }); },
  async endCombat() { return fetch("/api/playback/end_combat", { method: "POST" }); },
  async initialState() { return (await fetch("/api/playback/state")).json(); },
};

const isCombatName = (name) => /combat|batalha|boss/i.test(name || "");

// ---- Custom edge component -------------------------------------------------

// Renders a smoothstep edge plus a foreignObject label chip with the edge's
// text and an × button anchored to the midpoint. Clicking × calls data.onDelete.
// One custom edge type covers all three flavors (goto/stop/start) — the label
// text and delete callback come from data.
const SceneEdge = defineComponent({
  name: "SceneEdge",
  props: {
    id: { type: String, required: true },
    sourceX: Number, sourceY: Number,
    targetX: Number, targetY: Number,
    sourcePosition: String, targetPosition: String,
    markerEnd: [String, Object], style: Object,
    data: { type: Object, default: () => ({}) },
    animated: Boolean,
  },
  setup(props) {
    const pathParts = computed(() => getSmoothStepPath({
      sourceX: props.sourceX, sourceY: props.sourceY,
      sourcePosition: props.sourcePosition,
      targetX: props.targetX, targetY: props.targetY,
      targetPosition: props.targetPosition,
    }));
    return () => {
      const [path, labelX, labelY] = pathParts.value;
      return h(Fragment, [
        h(BaseEdge, {
          id: props.id,
          path,
          markerEnd: props.markerEnd,
          style: props.style,
          "class": props.animated ? "animated" : "",
        }),
        h(EdgeLabelRenderer, {}, () => h("div", {
          class: "edge-chip",
          style: {
            position: "absolute",
            transform: `translate(-50%, -50%) translate(${labelX}px, ${labelY}px)`,
            pointerEvents: "all",
          },
        }, [
          h("span", { class: "edge-chip-label" }, props.data.label || ""),
          h("button", {
            class: "edge-chip-delete",
            title: "remover conexão",
            onClick: (e) => { e.stopPropagation(); if (props.data.onDelete) props.data.onDelete(props.id); },
          }, "×"),
        ])),
      ]);
    };
  },
});

// ---- Custom node components ------------------------------------------------

// Stop node: singleton terminal. Any scene wired to it gets on_end: stop.
// Only has an incoming handle (source-less by design).
const StopNode = defineComponent({
  name: "StopNode",
  setup() {
    return () => h("div", { class: "special-node stop-node" }, [
      h(Handle, { type: "target", position: Position.Left }),
      h("div", { class: "special-node-icon" }, "⏹"),
      h("div", { class: "special-node-label" }, "fim"),
    ]);
  },
});

// Start node: singleton entry. Connecting start→scene marks that scene as
// the campaign entry (is_entry=true), and only one scene has it at a time.
// Source-only handle (no target — nothing "goes to" start).
const StartNode = defineComponent({
  name: "StartNode",
  setup() {
    return () => h("div", { class: "special-node start-node" }, [
      h("div", { class: "special-node-icon" }, "▶"),
      h("div", { class: "special-node-label" }, "início"),
      h(Handle, { type: "source", position: Position.Right }),
    ]);
  },
});

const SceneNode = defineComponent({
  name: "SceneNode",
  props: ["id", "data"],
  setup(props) {
    return () => h("div", {
      class: [
        "scene-node",
        props.data.playing ? "playing" : "",
        props.data.isCombat ? "combat" : "",
      ],
    }, [
      h(Handle, { type: "target", position: Position.Left }),
      h("div", { class: "head" }, [
        h("div", { class: "name" }, props.data.name),
      ]),
      h("div", { class: "meta" }, [
        `${props.data.layerCount} camada(s) · `,
        props.data.onEnd.type === "return_previous" ? "↩ retorna"
          : props.data.onEnd.type === "goto" ? "→ vai para outra"
          : "⏹ para",
      ]),
      h("div", { class: "actions" }, [
        h("button", {
          class: "play",
          onClick: (e) => { e.stopPropagation(); props.data.onPlay(); },
        }, "▶ tocar"),
        h("button", {
          onClick: (e) => { e.stopPropagation(); props.data.onEdit(); },
        }, "editar"),
        h("button", {
          class: "danger",
          title: "remover do mapa (não deleta a cena)",
          onClick: (e) => { e.stopPropagation(); props.data.onRemoveFromMap(); },
        }, "×"),
      ]),
      h(Handle, { type: "source", position: Position.Right }),
    ]);
  },
});

// ---- Live layer view (display-only waveform + moving playhead) ------------

const LayerLiveView = defineComponent({
  name: "LayerLiveView",
  props: {
    audioFileId: { type: String, required: true },
    label: { type: String, default: "" },
    layerState: { type: String, default: "idle" },
    positionMs: { type: Number, default: 0 },
    loopStartMs: { type: Number, default: null },
    loopEndMs: { type: Number, default: null },
  },
  setup(props) {
    const containerRef = ref(null);
    // Track the last authoritative position + when it landed, then
    // interpolate at ~30fps so the cursor moves smoothly between WS pings.
    let ws = null;
    let regionsPlugin = null;
    let loopRegion = null;
    let interpTimer = null;
    let lastPositionMs = props.positionMs;
    let lastUpdateAt = performance.now();
    let isReady = false;

    onMounted(() => {
      regionsPlugin = RegionsPlugin.create();
      ws = WaveSurfer.create({
        container: containerRef.value,
        waveColor: "#6c757d",
        progressColor: "#58a6ff",
        cursorColor: "#f85149",
        cursorWidth: 2,
        height: 48,
        barWidth: 1,
        barGap: 1,
        interact: false,
        url: `/api/uploads/${props.audioFileId}/download`,
        plugins: [regionsPlugin],
      });
      ws.on("ready", () => {
        isReady = true;
        if (props.loopStartMs != null && props.loopEndMs != null) {
          loopRegion = regionsPlugin.addRegion({
            start: props.loopStartMs / 1000,
            end: props.loopEndMs / 1000,
            color: "rgba(88, 166, 255, 0.15)",
            drag: false,
            resize: false,
          });
        }
        // Prime the interpolator with whatever position we've already been given
        lastPositionMs = props.positionMs;
        lastUpdateAt = performance.now();
        interpTimer = setInterval(() => {
          if (!ws || !isReady) return;
          const dur = ws.getDuration();
          if (!dur) return;
          // "playing" state -> extrapolate forward; other states -> stay put.
          let effective = lastPositionMs;
          if (props.layerState === "playing" || props.layerState === "fading_in") {
            effective = lastPositionMs + (performance.now() - lastUpdateAt);
          }
          const sec = Math.min(effective / 1000, dur);
          try { ws.setTime(sec); } catch (_) {}
        }, 1000 / 30);
      });
    });

    // Every time the WS ping brings a new position, reset the interpolator's
    // anchor so we don't drift.
    watch(() => props.positionMs, (newPos) => {
      lastPositionMs = newPos;
      lastUpdateAt = performance.now();
    });

    onBeforeUnmount(() => {
      if (interpTimer) clearInterval(interpTimer);
      if (ws) { try { ws.destroy(); } catch (_) {} ws = null; }
    });

    return { containerRef };
  },
  template: `
    <div class="layer-live">
      <div class="layer-live-head">
        <span>{{ label }}</span>
        <span class="state" :class="layerState">{{ layerState }}</span>
      </div>
      <div ref="containerRef" class="waveform-live"></div>
    </div>
  `,
});


// ---- Now Playing panel (right sidebar) ------------------------------------

const NowPlayingPanel = defineComponent({
  name: "NowPlayingPanel",
  components: { LayerLiveView: markRaw(LayerLiveView) },
  props: {
    scene: { type: Object, required: true },
    previousScene: { type: Object, default: null },
    engineLayers: { type: Object, required: true },  // scene_id::layer_id -> snapshot
  },
  emits: ["stop", "end-combat"],
  setup(props) {
    // For each layer in the current scene, pull runtime info from engineLayers.
    const rows = computed(() => props.scene.layers.map((layer, i) => {
      const key = `${props.scene.id}::${layer.id}`;
      const runtime = props.engineLayers[key] || {};
      return {
        key,
        layerId: layer.id,
        audioFileId: layer.audio_file_id,
        label: `camada ${i + 1}`,
        state: runtime.state || "idle",
        positionMs: runtime.position_ms || 0,
        loopStartMs: layer.loop_start_ms,
        loopEndMs: layer.loop_end_ms,
      };
    }));
    return { rows };
  },
  template: `
    <div class="np-header">
      <div class="section-title">tocando</div>
      <h2>{{ scene.name }}</h2>
      <div class="prev" v-if="previousScene">anterior: {{ previousScene.name }}</div>
    </div>
    <LayerLiveView
      v-for="row in rows"
      :key="row.key"
      :audio-file-id="row.audioFileId"
      :label="row.label"
      :layer-state="row.state"
      :position-ms="row.positionMs"
      :loop-start-ms="row.loopStartMs"
      :loop-end-ms="row.loopEndMs"
    />
    <div class="np-actions">
      <button class="end-combat" @click="$emit('end-combat')">FIM DE COMBATE</button>
      <button @click="$emit('stop')">■ parar</button>
    </div>
  `,
});


// ---- Loop region editor (waveform + draggable region) ---------------------

const LoopRegionEditor = defineComponent({
  name: "LoopRegionEditor",
  props: {
    audioFileId: { type: String, required: true },
    loopStartMs: { type: Number, default: null },
    loopEndMs: { type: Number, default: null },
  },
  emits: ["update"],
  setup(props, { emit }) {
    const containerRef = ref(null);
    const isPlaying = ref(false);
    const isReady = ref(false);
    // Kept in raw JS closures — Vue reactivity would fight with wavesurfer's
    // internal mutations and cause "maximum recursive updates" errors.
    let ws = null;
    let regionsPlugin = null;
    let region = null;

    const hasRegion = computed(
      () => props.loopStartMs != null && props.loopEndMs != null,
    );

    const emitUpdate = (startSec, endSec) => {
      emit("update", {
        loop_start_ms: Math.round(startSec * 1000),
        loop_end_ms: Math.round(endSec * 1000),
      });
    };

    const attachRegion = (startSec, endSec) => {
      if (region) region.remove();
      region = regionsPlugin.addRegion({
        start: startSec,
        end: endSec,
        color: "rgba(88, 166, 255, 0.25)",
        drag: true,
        resize: true,
      });
      // Wavesurfer fires "update-end" after the user finishes a drag/resize.
      region.on("update-end", () => {
        emitUpdate(region.start, region.end);
      });
    };

    const createDefaultRegion = () => {
      if (!ws || !isReady.value) return;
      const d = ws.getDuration();
      if (d <= 0) return;
      // Middle 60% of the file is usually a decent starting point for a loop.
      const start = d * 0.2;
      const end = d * 0.8;
      attachRegion(start, end);
      emitUpdate(start, end);
    };

    const clearRegion = () => {
      if (region) {
        region.remove();
        region = null;
      }
      emit("update", { loop_start_ms: null, loop_end_ms: null });
    };

    const togglePlay = () => {
      if (!ws || !isReady.value) return;
      ws.playPause();
    };

    onMounted(() => {
      regionsPlugin = RegionsPlugin.create();
      ws = WaveSurfer.create({
        container: containerRef.value,
        waveColor: "#8b949e",
        progressColor: "#58a6ff",
        cursorColor: "#f85149",
        cursorWidth: 2,
        height: 72,
        barWidth: 2,
        barGap: 1,
        url: `/api/uploads/${props.audioFileId}/download`,
        plugins: [regionsPlugin],
      });
      ws.on("ready", () => {
        isReady.value = true;
        if (hasRegion.value) {
          attachRegion(props.loopStartMs / 1000, props.loopEndMs / 1000);
        }
      });
      ws.on("play", () => (isPlaying.value = true));
      ws.on("pause", () => (isPlaying.value = false));
      ws.on("finish", () => (isPlaying.value = false));
    });

    onBeforeUnmount(() => {
      if (ws) {
        try { ws.destroy(); } catch (_) {}
        ws = null;
      }
    });

    return { containerRef, isPlaying, isReady, hasRegion, togglePlay, createDefaultRegion, clearRegion };
  },
  template: `
    <div class="loop-editor">
      <div ref="containerRef" class="waveform"></div>
      <div class="loop-editor-actions">
        <button type="button" @click="togglePlay" :disabled="!isReady">
          {{ isPlaying ? '⏸ pausar' : '▶ preview' }}
        </button>
        <button type="button" @click="createDefaultRegion" v-if="!hasRegion" :disabled="!isReady">
          + região de loop
        </button>
        <button type="button" class="danger" @click="clearRegion" v-else>
          remover região
        </button>
        <span class="loop-hint" v-if="hasRegion">
          arraste as bordas ou o centro da faixa azul pra ajustar
        </span>
      </div>
    </div>
  `,
});

// ---- Modal (create/edit scene) ---------------------------------------------

const SceneModal = defineComponent({
  name: "SceneModal",
  props: ["scene", "uploads"],
  emits: ["save", "close"],
  setup(props, { emit }) {
    const isEdit = !!props.scene;
    const name = ref(props.scene?.name || "");
    const description = ref(props.scene?.description || "");
    const layers = ref(props.scene ? props.scene.layers.map((l) => ({ ...l })) : []);

    const addLayer = () => {
      const first = props.uploads[0];
      if (!first) return;
      layers.value.push({
        audio_file_id: first.id,
        loop: true,
        volume: 0.8,
        fade_in_ms: 500,
        fade_out_ms: 500,
        loop_start_ms: null,
        loop_end_ms: null,
      });
    };
    const removeLayer = (i) => layers.value.splice(i, 1);
    const setLoopRegion = (i, { loop_start_ms, loop_end_ms }) => {
      layers.value[i].loop_start_ms = loop_start_ms;
      layers.value[i].loop_end_ms = loop_end_ms;
    };
    // When the user changes the audio file for a layer, previous loop markers
    // don't apply to the new waveform — clear them so wavesurfer re-mounts
    // fresh (component key uses audio_file_id).
    const onAudioFileChange = (i, newId) => {
      const layer = layers.value[i];
      if (layer.audio_file_id !== newId) {
        layer.audio_file_id = newId;
        layer.loop_start_ms = null;
        layer.loop_end_ms = null;
      }
    };

    const canSave = computed(() =>
      name.value.trim().length > 0 && layers.value.every((l) => l.audio_file_id)
    );

    const save = () => emit("save", {
      name: name.value.trim(),
      description: description.value.trim() || null,
      layers: layers.value,
      on_end: props.scene?.on_end || { type: "return_previous" },
    });

    return () => h("div", { class: "modal-backdrop", onClick: () => emit("close") }, [
      h("div", { class: "modal", onClick: (e) => e.stopPropagation() }, [
        h("h2", isEdit ? "editar cena" : "nova cena"),
        h("div", { class: "form-field" }, [
          h("label", "nome"),
          h("input", { type: "text", value: name.value, onInput: (e) => name.value = e.target.value }),
        ]),
        h("div", { class: "form-field" }, [
          h("label", "descrição"),
          h("textarea", { value: description.value, onInput: (e) => description.value = e.target.value }),
        ]),
        h("div", { class: "section-title" }, `camadas (${layers.value.length})`),
        ...layers.value.map((layer, i) => h("div", { key: i, class: "layer-editor" }, [
          h("div", { class: "layer-head" }, [
            h("h4", `camada ${i + 1}`),
            h("button", { class: "remove", onClick: () => removeLayer(i) }, "remover"),
          ]),
          h("div", { class: "form-field" }, [
            h("label", "arquivo"),
            h("select", {
              value: layer.audio_file_id,
              onChange: (e) => onAudioFileChange(i, e.target.value),
            }, props.uploads.map((f) => h("option", { value: f.id }, f.original_name))),
          ]),
          h("div", { class: "form-field" }, [
            h("label", `volume: ${Math.round(layer.volume * 100)}%`),
            h("input", {
              type: "range", min: 0, max: 1, step: 0.01, value: layer.volume,
              onInput: (e) => { layer.volume = parseFloat(e.target.value); },
            }),
          ]),
          h("label", { class: "checkbox" }, [
            h("input", {
              type: "checkbox", checked: layer.loop,
              onChange: (e) => { layer.loop = e.target.checked; },
            }),
            " loop",
          ]),
          // Waveform + region editor. Key on audio_file_id so switching
          // files remounts wavesurfer with the new source.
          layer.audio_file_id
            ? h(LoopRegionEditor, {
                key: layer.audio_file_id,
                audioFileId: layer.audio_file_id,
                loopStartMs: layer.loop_start_ms,
                loopEndMs: layer.loop_end_ms,
                onUpdate: (payload) => setLoopRegion(i, payload),
              })
            : null,
        ])),
        h("button", {
          style: "width: 100%; margin-top: 8px; padding: 10px; background: var(--panel-2); border: 1px solid var(--border); border-radius: 8px; color: var(--text); cursor: pointer;",
          disabled: props.uploads.length === 0,
          onClick: addLayer,
        }, props.uploads.length ? "+ adicionar camada" : "faça upload de áudio em / (aba áudios)"),
        h("div", { class: "form-actions" }, [
          h("button", {
            onClick: () => emit("close"),
            style: "background: transparent; border: 1px solid var(--border); border-radius: 8px; padding: 10px; color: var(--text); font-family: inherit; cursor: pointer;",
          }, "cancelar"),
          h("button", {
            disabled: !canSave.value,
            onClick: save,
            style: "background: var(--accent-strong); border: 1px solid var(--accent-strong); border-radius: 8px; padding: 10px; color: var(--text); font-family: inherit; cursor: pointer; font-weight: 600;",
          }, isEdit ? "salvar" : "criar"),
        ]),
      ]),
    ]);
  },
});

// ---- Root App --------------------------------------------------------------

const App = defineComponent({
  components: {
    VueFlow: markRaw(VueFlow),
    Background: markRaw(Background),
    Controls: markRaw(Controls),
    MiniMap: markRaw(MiniMap),
    SceneModal,
    NowPlayingPanel: markRaw(NowPlayingPanel),
  },
  setup() {
    const scenes = ref([]);
    const uploads = ref([]);
    const state = ref({
      current_scene_id: null,
      previous_scene_id: null,
      master_volume: 1.0,
      layers: {},
      xrun_count: 0,
    });
    const connected = ref(false);
    const modalOpen = ref(false);
    const modalScene = ref(null);
    const nodeTypes = markRaw({ scene: SceneNode, stop: StopNode, start: StartNode });
    const edgeTypes = markRaw({ "scene-edge": SceneEdge });

    // Special (non-scene) nodes live on the map alongside scene nodes but
    // aren't backed by rows in the scenes table. They must survive reconciliation.
    const STOP_NODE_ID = "__stop__";
    const START_NODE_ID = "__start__";
    const SPECIAL_NODE_IDS = new Set([STOP_NODE_ID, START_NODE_ID]);

    const loadPos = (key) => {
      try {
        const raw = localStorage.getItem(key);
        if (!raw) return null;
        const p = JSON.parse(raw);
        if (typeof p.x !== "number" || typeof p.y !== "number") return null;
        return p;
      } catch (_) { return null; }
    };
    const savePos = (key, pos) => {
      try { localStorage.setItem(key, JSON.stringify({ x: pos.x, y: pos.y })); } catch (_) {}
    };
    const STOP_POS_KEY = "loremaster-map-stop-position";
    const START_POS_KEY = "loremaster-map-start-position";

    // Delegate node ownership to Vue Flow: we call addNodes/removeNodes/
    // updateNodeData and read positions back from `vfNodes`. This way Vue Flow
    // owns `.position` (updated during drag) and we never overwrite it.
    const {
      nodes: vfNodes,
      edges: vfEdges,
      addNodes,
      removeNodes,
      updateNodeData,
      addEdges,
      removeEdges,
      project,
    } = useVueFlow();

    // Viewport persistence: restoring what the mestre was looking at feels much
    // better than fit-view snapping on every reload. localStorage is fine here
    // since /map is single-user single-device (see ROADMAP note: "mouse-first no notebook").
    const VIEWPORT_KEY = "loremaster-map-viewport";
    const loadViewport = () => {
      try {
        const raw = localStorage.getItem(VIEWPORT_KEY);
        if (!raw) return null;
        const v = JSON.parse(raw);
        if (typeof v.x !== "number" || typeof v.y !== "number" || typeof v.zoom !== "number") return null;
        return v;
      } catch (_) { return null; }
    };
    const storedViewport = loadViewport();
    const defaultViewport = storedViewport || { x: 0, y: 0, zoom: 0.9 };
    const shouldFitView = !storedViewport;
    const onViewportChangeEnd = (v) => {
      try { localStorage.setItem(VIEWPORT_KEY, JSON.stringify({ x: v.x, y: v.y, zoom: v.zoom })); } catch (_) {}
    };

    const buildNodeData = (scene) => ({
      name: scene.name,
      layerCount: scene.layers.length,
      onEnd: scene.on_end,
      playing: scene.id === state.value.current_scene_id,
      isCombat: isCombatName(scene.name),
      onPlay: () => API.play(scene.id),
      onEdit: () => openEdit(scene),
      onRemoveFromMap: () => removeFromMap(scene),
    });

    // Auto-layout for scenes newly added to the map without a position saved yet.
    const nextOpenSlot = (index) => {
      const step = 320, stepY = 140;
      const col = index % 4, row = Math.floor(index / 4);
      return { x: 60 + col * step, y: 60 + row * stepY };
    };

    // Reconcile Vue Flow's node collection with `scenes`:
    //  - remove nodes whose scene left the map / was deleted
    //  - add nodes for scenes that just entered the map
    //  - refresh `data` on remaining nodes via `updateNodeData` (doesn't touch position)
    //  - ensure special nodes (stop, start) are always present
    const reconcileNodes = () => {
      const onMap = scenes.value.filter((s) => s.is_on_map);
      const wantedIds = new Set(onMap.map((s) => s.id));
      const existingIds = new Set(vfNodes.value.map((n) => n.id));

      const toRemove = vfNodes.value
        .filter((n) => !SPECIAL_NODE_IDS.has(n.id) && !wantedIds.has(n.id))
        .map((n) => n.id);
      if (toRemove.length) removeNodes(toRemove);

      const toAdd = onMap.filter((s) => !existingIds.has(s.id));
      if (toAdd.length) {
        let slotCounter = vfNodes.value.length;
        addNodes(toAdd.map((s) => ({
          id: s.id,
          type: "scene",
          position: (s.graph_x != null && s.graph_y != null)
            ? { x: s.graph_x, y: s.graph_y }
            : nextOpenSlot(slotCounter++),
          data: buildNodeData(s),
        })));
      }

      for (const s of onMap) {
        if (existingIds.has(s.id)) updateNodeData(s.id, buildNodeData(s));
      }

      // Ensure the stop and start nodes are always on the canvas.
      // Not deletable via Delete key — they're campaign-graph landmarks.
      if (!existingIds.has(STOP_NODE_ID)) {
        addNodes([{
          id: STOP_NODE_ID,
          type: "stop",
          position: loadPos(STOP_POS_KEY) || { x: 900, y: 220 },
          data: {},
          deletable: false,
          selectable: true,
          draggable: true,
        }]);
      }
      if (!existingIds.has(START_NODE_ID)) {
        addNodes([{
          id: START_NODE_ID,
          type: "start",
          position: loadPos(START_POS_KEY) || { x: -180, y: 220 },
          data: {},
          deletable: false,
          selectable: true,
          draggable: true,
        }]);
      }
    };

    // Compute what edges *should* exist based on scenes; we reconcile Vue Flow's
    // internal edges collection below (parallel to how nodes are handled).
    // Three kinds: goto (scene→scene), stop (scene→__stop__), start (__start__→scene).
    // All render through the same SceneEdge component; the label + delete-callback
    // travel in data so a click on the × can persist via the same path.
    const buildEdgeData = (label) => ({ label, onDelete: deleteEdgeById });
    const desiredEdges = computed(() => {
      const onMap = scenes.value.filter((s) => s.is_on_map);
      const gotoEdges = onMap
        .filter((s) => s.on_end.type === "goto" && s.on_end.scene_id)
        .filter((s) => onMap.some((t) => t.id === s.on_end.scene_id))
        .map((s) => ({
          id: `e-${s.id}`,
          source: s.id,
          target: s.on_end.scene_id,
          type: "scene-edge",
          data: buildEdgeData("on_end"),
          animated: s.id === state.value.current_scene_id,
        }));
      const stopEdges = onMap
        .filter((s) => s.on_end.type === "stop")
        .map((s) => ({
          id: `e-${s.id}`,
          source: s.id,
          target: STOP_NODE_ID,
          type: "scene-edge",
          data: buildEdgeData("fim"),
          animated: s.id === state.value.current_scene_id,
        }));
      // Singleton start→entry_scene edge — at most one exists at a time.
      const entryScene = onMap.find((s) => s.is_entry);
      const startEdges = entryScene ? [{
        id: "e-start",
        source: START_NODE_ID,
        target: entryScene.id,
        type: "scene-edge",
        data: buildEdgeData("início"),
      }] : [];
      return [...gotoEdges, ...stopEdges, ...startEdges];
    });

    // Called from the × chip on the edge itself. desiredEdges is authoritative,
    // so look up there rather than in vfEdges (which may be mid-mutation).
    const deleteEdgeById = async (edgeId) => {
      const edge = desiredEdges.value.find((e) => e.id === edgeId);
      selectedEdgeId.value = null;
      if (edge) await persistEdgeRemoval(edge);
    };

    const reconcileEdges = () => {
      const wanted = desiredEdges.value;
      const wantedIds = new Set(wanted.map((e) => e.id));
      const existingIds = new Set(vfEdges.value.map((e) => e.id));

      const toRemove = vfEdges.value
        .filter((e) => !wantedIds.has(e.id))
        .map((e) => e.id);
      if (toRemove.length) removeEdges(toRemove);

      const toAdd = wanted.filter((e) => !existingIds.has(e.id));
      if (toAdd.length) addEdges(toAdd);
    };

    const reconcile = () => { reconcileNodes(); reconcileEdges(); };
    watch(scenes, reconcile, { deep: false });
    watch(() => state.value.current_scene_id, reconcile);

    const refreshScenes = async () => {
      scenes.value = await API.listScenes();
    };
    const refreshUploads = async () => { uploads.value = await API.listUploads(); };

    // ---- Actions -----------------------------------------------------------

    const onNodeDragStop = ({ node }) => {
      // Special nodes are client-only; persist their position in localStorage
      // instead of hitting the scenes API.
      if (node.id === STOP_NODE_ID) { savePos(STOP_POS_KEY, node.position); return; }
      if (node.id === START_NODE_ID) { savePos(START_POS_KEY, node.position); return; }
      API.setPosition(node.id, node.position.x, node.position.y);
      // Also update the local scenes cache so a subsequent full refresh
      // doesn't yank the node back to the old spot.
      const s = scenes.value.find((s) => s.id === node.id);
      if (s) { s.graph_x = node.position.x; s.graph_y = node.position.y; }
    };

    const onConnect = async ({ source, target }) => {
      // Dragging FROM the start node marks the target scene as campaign entry.
      if (source === START_NODE_ID) {
        if (SPECIAL_NODE_IDS.has(target)) return;
        await API.setEntryScene(target);
        await refreshScenes();
        return;
      }
      // Otherwise source must be a scene (stop/start don't have source→other).
      if (SPECIAL_NODE_IDS.has(source)) return;
      if (target === STOP_NODE_ID) {
        await API.setOnEnd(source, { type: "stop" });
      } else if (!SPECIAL_NODE_IDS.has(target)) {
        await API.setOnEnd(source, { type: "goto", scene_id: target });
      }
      await refreshScenes();
    };

    // Route edge deletion based on the edge's kind: goto/stop edges reset the
    // source scene's on_end; start edges clear the entry scene singleton.
    const persistEdgeRemoval = async (edge) => {
      if (edge.source === START_NODE_ID) {
        await API.setEntryScene(null);
      } else {
        await API.setOnEnd(edge.source, { type: "return_previous" });
      }
      await refreshScenes();
    };

    // Select-then-delete pattern: clicking an edge just selects it (Vue Flow
    // already highlights .selected via CSS). The toolbar button (or Delete key)
    // then removes the selected edge. Avoids a scary confirm() on every click.
    const selectedEdgeId = ref(null);

    const onEdgeClick = ({ edge }) => {
      selectedEdgeId.value = edge.id;
    };

    const onPaneClick = () => { selectedEdgeId.value = null; };

    const deleteSelectedEdge = async () => {
      const id = selectedEdgeId.value;
      if (!id) return;
      // Look up in desiredEdges (source of truth from scenes) rather than vfEdges,
      // which may have already been mutated if this fires from the keyboard path.
      const edge = desiredEdges.value.find((e) => e.id === id)
                || vfEdges.value.find((e) => e.id === id);
      selectedEdgeId.value = null;
      if (edge) await persistEdgeRemoval(edge);
    };

    // When Vue Flow's delete-key path removes an edge, vfEdges has already been
    // mutated by the time this handler runs. Look up the edge in desiredEdges
    // instead — it's computed from scenes (which hasn't changed yet), so the
    // just-removed edge is still there for us to persist.
    const onEdgesChange = async (changes) => {
      for (const c of changes) {
        if (c.type === "remove") {
          const edge = desiredEdges.value.find((e) => e.id === c.id);
          if (edge) await persistEdgeRemoval(edge);
        }
      }
    };
    const onEdgesDelete = async (deletedEdges) => {
      for (const e of deletedEdges) await persistEdgeRemoval(e);
    };

    // Delete key on a selected card fires nodesChange with type "remove"
    // (this Vue Flow version doesn't emit nodesDelete for the keyboard path).
    // Persist as setOnMap(false) so re-adding from the palette works cleanly.
    // Special nodes (stop, start) are skipped — they aren't backed by a scene row.
    const onNodesChange = async (changes) => {
      const removals = changes.filter((c) => c.type === "remove" && !SPECIAL_NODE_IDS.has(c.id));
      for (const c of removals) {
        await API.setOnMap(c.id, false);
      }
      if (removals.length) await refreshScenes();
    };

    const addToMap = async (scene) => {
      // Place near center of the current viewport for a bit more polish
      await API.setOnMap(scene.id, true);
      await refreshScenes();
    };

    const removeFromMap = async (scene) => {
      await API.setOnMap(scene.id, false);
      await refreshScenes();
    };

    const openEdit = (scene) => { modalScene.value = scene; modalOpen.value = true; };
    const openCreate = () => { modalScene.value = null; modalOpen.value = true; };

    const saveModal = async (payload) => {
      if (modalScene.value) {
        const r = await fetch(`/api/scenes/${modalScene.value.id}`, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!r.ok) { alert(await r.text()); return; }
      } else {
        const created = await API.createScene(payload);
        if (!created) { alert("falha ao criar cena"); return; }
      }
      modalOpen.value = false;
      await refreshScenes();
    };

    // ---- Drag from palette to canvas ---------------------------------------

    const canvasRef = ref(null);

    const onPaletteDragStart = (scene, event) => {
      event.dataTransfer.setData("application/x-loremaster-scene", scene.id);
      event.dataTransfer.effectAllowed = "move";
    };

    const onCanvasDragOver = (event) => {
      event.preventDefault();
      event.dataTransfer.dropEffect = "move";
    };

    // Approximate scene-node dimensions from map.css (min 200, max 260 wide;
     // height grows with layer count but hovers around 110). Centering the drop
     // under the cursor feels much better than the top-left default.
    const NODE_HALF_W = 115;
    const NODE_HALF_H = 55;

    const onCanvasDrop = async (event) => {
      event.preventDefault();
      const sceneId = event.dataTransfer.getData("application/x-loremaster-scene");
      if (!sceneId) return;
      const scene = scenes.value.find((s) => s.id === sceneId);
      if (!scene || scene.is_on_map) return;
      // Convert screen coords to canvas coords using Vue Flow's projector,
      // then shift back by half the card size so the cursor ends up at the center.
      const rect = event.currentTarget.getBoundingClientRect();
      const projected = project({ x: event.clientX - rect.left, y: event.clientY - rect.top });
      const position = { x: projected.x - NODE_HALF_W, y: projected.y - NODE_HALF_H };
      await API.setOnMap(sceneId, true, position);
      await refreshScenes();
    };

    // ---- Palette items -----------------------------------------------------

    const paletteScenes = computed(() =>
      [...scenes.value].sort((a, b) => {
        // Show off-map first (actionable), then on-map (informational)
        if (a.is_on_map !== b.is_on_map) return a.is_on_map ? 1 : -1;
        return a.name.localeCompare(b.name);
      })
    );

    // ---- WebSocket ---------------------------------------------------------

    let ws = null, reconnectTimer = null;
    const connectWs = () => {
      const proto = location.protocol === "https:" ? "wss" : "ws";
      ws = new WebSocket(`${proto}://${location.host}/ws`);
      ws.onopen = () => { connected.value = true; };
      ws.onclose = () => {
        connected.value = false;
        reconnectTimer = setTimeout(connectWs, 1000);
      };
      ws.onerror = () => ws && ws.close();
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg.type === "state") {
            state.value = {
              current_scene_id: msg.current_scene_id,
              previous_scene_id: msg.previous_scene_id,
              master_volume: msg.master_volume,
              layers: msg.layers || {},
              xrun_count: msg.xrun_count,
            };
          }
        } catch (_) {}
      };
    };

    // Delete/Backspace removes the currently selected edge. Guard against
    // stealing keys when the user is typing in an input/textarea (modal).
    const onKeyDown = (e) => {
      if (e.key !== "Delete" && e.key !== "Backspace") return;
      const tag = (e.target && e.target.tagName) || "";
      if (tag === "INPUT" || tag === "TEXTAREA" || e.target?.isContentEditable) return;
      if (selectedEdgeId.value) {
        e.preventDefault();
        deleteSelectedEdge();
      }
    };

    onMounted(async () => {
      connectWs();
      window.addEventListener("keydown", onKeyDown);
      await Promise.all([refreshScenes(), refreshUploads()]);
      state.value = await API.initialState();
    });

    onBeforeUnmount(() => {
      window.removeEventListener("keydown", onKeyDown);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      if (ws) ws.close();
    });

    const currentScene = computed(() =>
      scenes.value.find((s) => s.id === state.value.current_scene_id) || null
    );
    const previousScene = computed(() =>
      scenes.value.find((s) => s.id === state.value.previous_scene_id) || null
    );

    return {
      scenes, uploads, nodeTypes, edgeTypes, connected, state,
      modalOpen, modalScene, paletteScenes, canvasRef,
      currentScene, previousScene, selectedEdgeId,
      defaultViewport, shouldFitView, onViewportChangeEnd,
      onNodeDragStop, onConnect, onEdgesChange, onEdgesDelete, onEdgeClick, onPaneClick, onNodesChange,
      addToMap, removeFromMap, openCreate, saveModal, deleteSelectedEdge,
      onPaletteDragStart, onCanvasDragOver, onCanvasDrop,
      stop: () => API.stop(),
      endCombat: () => API.endCombat(),
    };
  },
  template: `
    <div class="map-toolbar">
      <h1>Loremaster — mapa de campanha</h1>
      <div class="actions">
        <span class="status">
          <span class="dot" :class="connected ? 'on' : 'off'"></span>
          {{ connected ? 'conectado' : 'reconectando…' }}
          <span v-if="state.xrun_count > 0" style="color: var(--warning); margin-left: 8px;">
            xruns: {{ state.xrun_count }}
          </span>
        </span>
        <button class="primary" @click="openCreate">+ nova cena</button>
        <button
          class="danger"
          :disabled="!selectedEdgeId"
          @click="deleteSelectedEdge"
          :title="selectedEdgeId ? 'remover conexão selecionada (Del)' : 'selecione uma aresta pra remover'"
        >× remover conexão</button>
        <a href="/" style="color: var(--muted); font-size: 12px; text-decoration: none; margin-left: 8px;">↗ controle</a>
      </div>
    </div>

    <div class="workspace" :class="{ 'has-now-playing': !!currentScene }">
      <aside class="palette">
        <h2>cenas disponíveis</h2>
        <div v-if="paletteScenes.length === 0" class="empty">
          nenhuma cena — clique em "+ nova cena" acima
        </div>
        <div
          v-for="s in paletteScenes"
          :key="s.id"
          class="palette-item"
          :class="{ 'on-map': s.is_on_map }"
          draggable="true"
          @dragstart="onPaletteDragStart(s, $event)"
          :title="s.is_on_map ? 'já está no mapa (arraste do mapa pra mover)' : 'arraste para o canvas ou clique em adicionar'"
        >
          <div class="info">
            <div class="name">{{ s.name }}</div>
            <div class="meta">
              {{ s.layers.length }} camada(s)
              <span v-if="s.is_on_map"> · no mapa</span>
            </div>
          </div>
          <button
            class="add-btn"
            :class="{ remove: s.is_on_map }"
            @click="s.is_on_map ? removeFromMap(s) : addToMap(s)"
          >{{ s.is_on_map ? 'remover' : '+ adicionar' }}</button>
        </div>
      </aside>

      <div
        class="canvas"
        ref="canvasRef"
        @dragover="onCanvasDragOver"
        @drop="onCanvasDrop"
      >
        <VueFlow
          :node-types="nodeTypes"
          :edge-types="edgeTypes"
          :default-viewport="defaultViewport"
          :min-zoom="0.3"
          :max-zoom="1.6"
          :snap-to-grid="true"
          :snap-grid="[16, 16]"
          :delete-key-code="['Delete', 'Backspace']"
          :fit-view-on-init="shouldFitView"
          @node-drag-stop="onNodeDragStop"
          @connect="onConnect"
          @edge-click="onEdgeClick"
          @pane-click="onPaneClick"
          @edges-change="onEdgesChange"
          @edges-delete="onEdgesDelete"
          @nodes-change="onNodesChange"
          @viewport-change-end="onViewportChangeEnd"
        >
          <Background :gap="16" :size="1" pattern-color="#30363d" />
          <Controls />
          <MiniMap pannable zoomable :node-color="'#1f6feb'" :node-stroke-color="'#58a6ff'" />
        </VueFlow>
      </div>

      <aside v-if="currentScene" class="now-playing-panel">
        <NowPlayingPanel
          :scene="currentScene"
          :previous-scene="previousScene"
          :engine-layers="state.layers || {}"
          @stop="stop"
          @end-combat="endCombat"
        />
      </aside>
    </div>

    <SceneModal
      v-if="modalOpen"
      :scene="modalScene"
      :uploads="uploads"
      @save="saveModal"
      @close="modalOpen = false"
    />
  `,
});

createApp(App).mount("#app");
