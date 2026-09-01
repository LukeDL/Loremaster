// Loremaster — campaign map (node graph editor).
// Vue 3 + Vue Flow via import map (see map.html).
// Palette (left) lists every scene; canvas (right) shows only opt-in ones.

import { createApp, ref, computed, onMounted, onBeforeUnmount, watch, defineComponent, h, markRaw, nextTick, reactive } from "vue";
import { VueFlow, Handle, Position, useVueFlow } from "@vue-flow/core";
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

// ---- Custom node component -------------------------------------------------

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
    const nodeTypes = markRaw({ scene: SceneNode });

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
    const reconcileNodes = () => {
      const onMap = scenes.value.filter((s) => s.is_on_map);
      const wantedIds = new Set(onMap.map((s) => s.id));
      const existingIds = new Set(vfNodes.value.map((n) => n.id));

      const toRemove = vfNodes.value
        .filter((n) => !wantedIds.has(n.id))
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
    };

    // Compute what edges *should* exist based on scenes; we reconcile Vue Flow's
    // internal edges collection below (parallel to how nodes are handled).
    const desiredEdges = computed(() =>
      scenes.value
        .filter((s) => s.is_on_map && s.on_end.type === "goto" && s.on_end.scene_id)
        .filter((s) => scenes.value.some((t) => t.id === s.on_end.scene_id && t.is_on_map))
        .map((s) => ({
          id: `e-${s.id}`,
          source: s.id,
          target: s.on_end.scene_id,
          label: "on_end",
          type: "smoothstep",
          animated: s.id === state.value.current_scene_id,
        }))
    );

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
      API.setPosition(node.id, node.position.x, node.position.y);
      // Also update the local scenes cache so a subsequent full refresh
      // doesn't yank the node back to the old spot.
      const s = scenes.value.find((s) => s.id === node.id);
      if (s) { s.graph_x = node.position.x; s.graph_y = node.position.y; }
    };

    const onConnect = async ({ source, target }) => {
      await API.setOnEnd(source, { type: "goto", scene_id: target });
      await refreshScenes();
    };

    const persistEdgeRemoval = async (sourceId) => {
      await API.setOnEnd(sourceId, { type: "return_previous" });
      await refreshScenes();
    };

    // Direct UI action: click on an edge -> confirm -> delete.
    // The Delete-key path via Vue Flow's edgesDelete is fragile in the
    // controlled-mode setup, so click-to-delete is the primary interaction.
    const onEdgeClick = ({ edge }) => {
      const target = scenes.value.find((s) => s.id === edge.target);
      const source = scenes.value.find((s) => s.id === edge.source);
      const label = source && target
        ? `${source.name} → ${target.name}`
        : "esta conexão";
      if (confirm(`Remover a conexão ${label}?`)) {
        persistEdgeRemoval(edge.source);
      }
    };

    // Keep these too, in case the Delete key ever starts firing —
    // idempotent because persist just sets on_end to return_previous.
    const onEdgesChange = async (changes) => {
      for (const c of changes) {
        if (c.type === "remove") await persistEdgeRemoval(c.id.replace(/^e-/, ""));
      }
    };
    const onEdgesDelete = async (deletedEdges) => {
      for (const e of deletedEdges) await persistEdgeRemoval(e.source);
    };

    // Delete key on a selected card fires nodesChange with type "remove"
    // (this Vue Flow version doesn't emit nodesDelete for the keyboard path).
    // Persist as setOnMap(false) so re-adding from the palette works cleanly.
    const onNodesChange = async (changes) => {
      const removals = changes.filter((c) => c.type === "remove");
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

    const onCanvasDrop = async (event) => {
      event.preventDefault();
      const sceneId = event.dataTransfer.getData("application/x-loremaster-scene");
      if (!sceneId) return;
      const scene = scenes.value.find((s) => s.id === sceneId);
      if (!scene || scene.is_on_map) return;
      // Convert screen coords to canvas coords using Vue Flow's projector
      const rect = event.currentTarget.getBoundingClientRect();
      const position = project({ x: event.clientX - rect.left, y: event.clientY - rect.top });
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

    onMounted(async () => {
      connectWs();
      await Promise.all([refreshScenes(), refreshUploads()]);
      state.value = await API.initialState();
    });

    onBeforeUnmount(() => {
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
      scenes, uploads, nodeTypes, connected, state,
      modalOpen, modalScene, paletteScenes, canvasRef,
      currentScene, previousScene,
      onNodeDragStop, onConnect, onEdgesChange, onEdgesDelete, onEdgeClick, onNodesChange,
      addToMap, removeFromMap, openCreate, saveModal,
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
          :default-viewport="{ x: 0, y: 0, zoom: 0.9 }"
          :min-zoom="0.3"
          :max-zoom="1.6"
          :snap-to-grid="true"
          :snap-grid="[16, 16]"
          :delete-key-code="['Delete', 'Backspace']"
          fit-view-on-init
          @node-drag-stop="onNodeDragStop"
          @connect="onConnect"
          @edge-click="onEdgeClick"
          @edges-change="onEdgesChange"
          @edges-delete="onEdgesDelete"
          @nodes-change="onNodesChange"
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
