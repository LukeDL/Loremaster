// Loremaster control panel — Vue 3 (ESM via import map, no build step).
// Three views: Scenes (play), Uploads (audio files), Editor (create/edit scenes).
// The footer with FIM DA CENA / stop / master volume is visible on every view.

import { createApp, ref, computed, onMounted, onBeforeUnmount, watch, reactive, markRaw } from "vue";
import { LoopRegionEditor } from "/waveform-editor.js";

// ---- API ---------------------------------------------------------------------

const API = {
  async listScenes() { return (await fetch("/api/scenes")).json(); },
  async getScene(id) { return (await fetch(`/api/scenes/${id}`)).json(); },
  async createScene(payload) {
    return fetch("/api/scenes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  async updateScene(id, payload) {
    return fetch(`/api/scenes/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
  },
  async deleteScene(id) { return fetch(`/api/scenes/${id}`, { method: "DELETE" }); },
  async listUploads() { return (await fetch("/api/uploads")).json(); },
  async uploadFile(file) {
    const form = new FormData();
    form.append("file", file);
    return fetch("/api/uploads", { method: "POST", body: form });
  },
  async deleteUpload(id) { return fetch(`/api/uploads/${id}`, { method: "DELETE" }); },
  async play(sceneId) {
    return fetch("/api/playback/play", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ scene_id: sceneId }),
    });
  },
  async stop() { return fetch("/api/playback/stop", { method: "POST" }); },
  async endScene() { return fetch("/api/playback/end_scene", { method: "POST" }); },
  async setVolume(target, volume) {
    return fetch("/api/playback/volume", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ target, volume }),
    });
  },
  async patchLayer(layerId, values) {
    return fetch(`/api/playback/layers/${layerId}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(values),
    });
  },
  async setGroupVolume(group, volume) {
    return fetch(`/api/playback/groups/${group}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ volume }),
    });
  },
  async initialState() { return (await fetch("/api/playback/state")).json(); },
};

function debounce(fn, ms) {
  let t;
  return (...args) => {
    clearTimeout(t);
    t = setTimeout(() => fn(...args), ms);
  };
}

function debounceByKey(fn, ms) {
  const timers = new Map();
  return (key, ...args) => {
    clearTimeout(timers.get(key));
    timers.set(key, setTimeout(() => {
      timers.delete(key);
      fn(key, ...args);
    }, ms));
  };
}

function formatBytes(n) {
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  return `${(n / 1024 / 1024).toFixed(1)} MB`;
}

function formatDuration(ms) {
  const s = Math.round(ms / 1000);
  const m = Math.floor(s / 60);
  const r = s % 60;
  return m > 0 ? `${m}:${String(r).padStart(2, "0")}` : `${r}s`;
}

// ---- Shared app store (view-agnostic state) ---------------------------------

const store = reactive({
  view: "scenes",  // "scenes" | "uploads" | "editor"
  editingSceneId: null,  // when view === "editor" and editing existing
  scenes: [],
  uploads: [],
  state: {
    current_scene_id: null,
    previous_scene_id: null,
    master_volume: 1.0,
    group_volumes: { music: 1.0, ambience: 1.0, sfx: 1.0 },
    layers: {},
    xrun_count: 0,
  },
  connected: false,
  error: null,
});

async function refreshScenes() { store.scenes = await API.listScenes(); }
async function refreshUploads() { store.uploads = await API.listUploads(); }

function goto(view, sceneId = null) {
  store.view = view;
  store.editingSceneId = sceneId;
  store.error = null;
}

async function reportFetch(res, action) {
  if (!res.ok) {
    const detail = await res.text().catch(() => res.statusText);
    store.error = `${action}: ${res.status} ${detail}`;
    return false;
  }
  return true;
}

// ---- WebSocket wiring --------------------------------------------------------

function connectWebSocket() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  const url = `${proto}://${location.host}/ws`;
  let ws = null;
  let reconnectTimer = null;

  const open = () => {
    ws = new WebSocket(url);
    ws.onopen = () => (store.connected = true);
    ws.onclose = () => {
      store.connected = false;
      reconnectTimer = setTimeout(open, 1000);
    };
    ws.onerror = () => ws && ws.close();
    ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data);
        if (msg.type === "state") {
          store.state.current_scene_id = msg.current_scene_id;
          store.state.previous_scene_id = msg.previous_scene_id;
          store.state.master_volume = msg.master_volume;
          store.state.group_volumes = msg.group_volumes;
          store.state.layers = msg.layers;
          store.state.xrun_count = msg.xrun_count;
        }
      } catch (e) { console.warn("bad ws payload", e); }
    };
  };
  open();
  return () => {
    if (reconnectTimer) clearTimeout(reconnectTimer);
    if (ws) ws.close();
  };
}

// ---- View: Scenes -----------------------------------------------------------

const ScenesView = {
  setup() {
    const currentScene = computed(() =>
      store.scenes.find((s) => s.id === store.state.current_scene_id) || null
    );
    const previousScene = computed(() =>
      store.scenes.find((s) => s.id === store.state.previous_scene_id) || null
    );

    const localLayerMix = ref({});
    watch(() => store.state.layers, (layers) => {
      for (const [lid, info] of Object.entries(layers)) {
        const bare = lid.includes("::") ? lid.split("::").slice(1).join("::") : lid;
        if (bare.includes("__old_")) continue;  // skip crossfade ghost layers
        const layer = currentScene.value?.layers.find((item) => item.id === bare);
        if (!layer) continue;
        const groupVolume = store.state.group_volumes[layer.group] ?? 1.0;
        localLayerMix.value[bare] = {
          volume: groupVolume > 0 ? info.volume / groupVolume : layer.volume,
          pan_lr: info.pan_lr ?? layer.pan_lr,
        };
      }
    }, { deep: true });

    const pushLayerMix = debounceByKey(async (layerId, values) => {
      const res = await API.patchLayer(layerId, values);
      await reportFetch(res, "ajustar camada");
    }, 100);
    const setLayerVol = (layerId, v) => {
      localLayerMix.value[layerId] = { ...localLayerMix.value[layerId], volume: v };
      pushLayerMix(layerId, { volume: v });
    };
    const setLayerPan = (layerId, v) => {
      localLayerMix.value[layerId] = { ...localLayerMix.value[layerId], pan_lr: v };
      pushLayerMix(layerId, { pan_lr: v });
    };

    const currentLayerRows = computed(() => {
      const scene = currentScene.value;
      if (!scene) return [];
      return scene.layers.map((layer, i) => {
        const engineKey = `${scene.id}::${layer.id}`;
        const runtime = store.state.layers[engineKey] || {};
        return {
          id: layer.id,
          index: i + 1,
          state: runtime.state || "idle",
          volume: localLayerMix.value[layer.id]?.volume ?? layer.volume,
          pan_lr: localLayerMix.value[layer.id]?.pan_lr ?? layer.pan_lr,
          group: layer.group,
          loop: layer.loop,
        };
      });
    });

    const playScene = async (sceneId) => {
      await reportFetch(await API.play(sceneId), "tocar cena");
    };

    const setGroupVol = debounceByKey(async (group, volume) => {
      store.state.group_volumes[group] = volume;
      await reportFetch(await API.setGroupVolume(group, volume), `ajustar grupo ${group}`);
    }, 100);

    const deleteScene = async (scene) => {
      if (!confirm(`Deletar cena "${scene.name}"?`)) return;
      const res = await API.deleteScene(scene.id);
      if (await reportFetch(res, "deletar cena")) await refreshScenes();
    };

    return {
      store, currentScene, previousScene, currentLayerRows,
      playScene, deleteScene, setLayerVol, setLayerPan, setGroupVol, goto,
    };
  },
  template: `
    <div>
      <div class="now-playing" :class="{ empty: !currentScene }">
        <template v-if="currentScene">
          <div class="section-title">tocando</div>
          <h2>{{ currentScene.name }}</h2>
          <div class="prev" v-if="previousScene">anterior: {{ previousScene.name }}</div>
          <div class="group-mixer" aria-label="Volumes dos grupos">
            <label v-for="group in ['music', 'ambience', 'sfx']" :key="group">
              <span>{{ group === 'music' ? 'música' : group === 'ambience' ? 'ambiente' : 'SFX' }}</span>
              <input type="range" min="0" max="1" step="0.01"
                     :aria-label="'Volume do grupo ' + group"
                     :value="store.state.group_volumes[group]"
                     @input="setGroupVol(group, parseFloat($event.target.value))" />
              <span>{{ Math.round(store.state.group_volumes[group] * 100) }}%</span>
            </label>
          </div>
          <div v-for="row in currentLayerRows" :key="row.id" class="layer-row">
            <div>
              <div class="label">
                camada {{ row.index }} · {{ row.group }}
                <span class="state" :class="row.state">{{ row.state }}</span>
                <span v-if="row.loop" style="color: var(--muted); font-size: 10px;">↻</span>
              </div>
              <input type="range" min="0" max="1" step="0.01"
                     :aria-label="'Volume da camada ' + row.index"
                     :value="row.volume"
                     @input="setLayerVol(row.id, parseFloat($event.target.value))" />
              <input type="range" min="-1" max="1" step="0.01"
                     :aria-label="'Pan da camada ' + row.index"
                     :value="row.pan_lr"
                     @input="setLayerPan(row.id, parseFloat($event.target.value))" />
            </div>
            <div class="layer-values">
              <span>{{ Math.round(row.volume * 100) }}%</span>
              <span>pan {{ row.pan_lr > 0 ? '+' : '' }}{{ row.pan_lr.toFixed(2) }}</span>
            </div>
          </div>
        </template>
        <template v-else>
          nada tocando
        </template>
      </div>

      <div class="header-actions">
        <div class="section-title" style="margin-bottom: 0;">cenas ({{ store.scenes.length }})</div>
        <button @click="goto('editor')">+ nova cena</button>
      </div>

      <div v-if="store.scenes.length === 0" class="empty-state">
        nenhuma cena ainda —
        <a href="#" @click.prevent="goto('editor')" style="color: var(--accent);">criar a primeira</a>
      </div>
      <div class="scenes-grid">
        <div v-for="scene in store.scenes" :key="scene.id"
             class="scene-card"
             :class="{ playing: currentScene && scene.id === currentScene.id }">
          <div @click="playScene(scene.id)" @keydown.enter="playScene(scene.id)"
               @keydown.space.prevent="playScene(scene.id)" role="button" tabindex="0"
               :aria-label="'Tocar cena ' + scene.name" style="flex: 1;">
            <div class="name">{{ scene.name }}</div>
            <div class="meta">
              {{ scene.layers.length }} camada(s) ·
              {{ scene.on_end.type === 'return_previous' ? '↩ retorna'
               : scene.on_end.type === 'goto' ? '→ vai para outra'
               : '⏹ para' }}
            </div>
          </div>
          <div class="actions">
            <button @click.stop="goto('editor', scene.id)">editar</button>
            <button class="danger" @click.stop="deleteScene(scene)">deletar</button>
          </div>
        </div>
      </div>
    </div>
  `,
};

// ---- View: Uploads ----------------------------------------------------------

const UploadsView = {
  setup() {
    const dragging = ref(false);
    const uploading = ref([]);  // [{name, progress}]

    const doUpload = async (files) => {
      for (const file of files) {
        const entry = reactive({ name: file.name, progress: "enviando…" });
        uploading.value.push(entry);
        const res = await API.uploadFile(file);
        if (!res.ok) {
          const detail = await res.text().catch(() => res.statusText);
          entry.progress = `falhou: ${res.status} ${detail}`;
          continue;
        }
        entry.progress = "ok";
        // remove after 800ms
        setTimeout(() => {
          const i = uploading.value.indexOf(entry);
          if (i >= 0) uploading.value.splice(i, 1);
        }, 800);
      }
      await refreshUploads();
    };

    const onDrop = (e) => {
      e.preventDefault();
      dragging.value = false;
      doUpload(Array.from(e.dataTransfer.files));
    };
    const onPick = (e) => doUpload(Array.from(e.target.files));

    const deleteFile = async (file) => {
      if (!confirm(`Deletar "${file.original_name}"?`)) return;
      const res = await API.deleteUpload(file.id);
      if (await reportFetch(res, "deletar arquivo")) await refreshUploads();
    };

    onMounted(refreshUploads);

    return { store, dragging, uploading, onDrop, onPick, deleteFile, formatBytes, formatDuration };
  },
  template: `
    <div>
      <label class="upload-zone"
             :class="{ dragging }"
             @dragover.prevent="dragging = true"
             @dragleave.prevent="dragging = false"
             @drop="onDrop">
        <div class="primary">arraste arquivos de áudio aqui</div>
        <div style="margin-top: 4px; font-size: 12px;">ou toque para escolher (wav, ogg, flac, mp3, opus)</div>
        <input type="file" multiple accept="audio/*,.wav,.ogg,.flac,.mp3,.opus,.oga,.aiff,.aif" @change="onPick" />
      </label>

      <div v-for="entry in uploading" :key="entry.name" class="upload-progress">
        <strong>{{ entry.name }}</strong> — {{ entry.progress }}
      </div>

      <div class="section-title">{{ store.uploads.length }} arquivo(s)</div>
      <div v-if="store.uploads.length === 0" class="empty-state">nenhum arquivo ainda</div>
      <div v-for="file in store.uploads" :key="file.id" class="file-row">
        <div>
          <div class="name">{{ file.original_name }}</div>
          <div class="meta">
            {{ formatDuration(file.duration_ms) }} ·
            {{ file.sample_rate }} Hz · {{ file.channels }}ch ·
            {{ formatBytes(file.size_bytes) }}
          </div>
        </div>
        <button @click="deleteFile(file)">deletar</button>
      </div>
    </div>
  `,
};

// ---- View: Editor -----------------------------------------------------------

const EditorView = {
  setup() {
    const form = reactive({
      name: "",
      description: "",
      layers: [],  // [{audio_file_id, loop, volume, fade_in_ms, fade_out_ms, loop_start_ms, loop_end_ms}]
      group_volumes: { music: 1.0, ambience: 1.0, sfx: 1.0 },
      on_end: { type: "return_previous" },  // or {type:"goto", scene_id} or {type:"stop"}
    });
    const saving = ref(false);
    const isEditing = computed(() => !!store.editingSceneId);

    const load = async () => {
      // Uploads always needed for the layer dropdown
      if (store.uploads.length === 0) await refreshUploads();
      if (store.editingSceneId) {
        const scene = await API.getScene(store.editingSceneId);
        form.name = scene.name;
        form.description = scene.description || "";
        form.group_volumes = { ...scene.group_volumes };
        form.layers = scene.layers.map((l) => ({
          id: l.id,
          audio_file_id: l.audio_file_id,
          loop: l.loop,
          volume: l.volume,
          pan_lr: l.pan_lr,
          group: l.group,
          fade_in_ms: l.fade_in_ms,
          fade_out_ms: l.fade_out_ms,
          loop_start_ms: l.loop_start_ms ?? null,
          loop_end_ms: l.loop_end_ms ?? null,
        }));
        form.on_end = { ...scene.on_end };
      } else {
        form.name = "";
        form.description = "";
        form.layers = [];
        form.group_volumes = { music: 1.0, ambience: 1.0, sfx: 1.0 };
        form.on_end = { type: "return_previous" };
      }
    };

    onMounted(load);
    watch(() => store.editingSceneId, load);

    const addLayer = () => {
      const firstFile = store.uploads[0];
      form.layers.push({
        audio_file_id: firstFile ? firstFile.id : "",
        loop: true,
        volume: 0.8,
        pan_lr: 0.0,
        group: "ambience",
        fade_in_ms: 500,
        fade_out_ms: 500,
        loop_start_ms: null,
        loop_end_ms: null,
      });
    };

    const removeLayer = (i) => { form.layers.splice(i, 1); };

    // Switching audio files invalidates the loop markers (they were positions
    // in a different waveform). Clearing forces the waveform editor to remount.
    const onAudioFileChange = (i, newId) => {
      const layer = form.layers[i];
      if (layer.audio_file_id !== newId) {
        layer.audio_file_id = newId;
        layer.loop_start_ms = null;
        layer.loop_end_ms = null;
      }
    };

    const setLoopRegion = (i, { loop_start_ms, loop_end_ms }) => {
      form.layers[i].loop_start_ms = loop_start_ms;
      form.layers[i].loop_end_ms = loop_end_ms;
    };

    const setOnEndType = (t) => {
      if (t === "return_previous") form.on_end = { type: "return_previous" };
      else if (t === "stop") form.on_end = { type: "stop" };
      else if (t === "goto") {
        const first = store.scenes.find((s) => s.id !== store.editingSceneId);
        form.on_end = { type: "goto", scene_id: first ? first.id : "" };
      }
    };

    const canSave = computed(() =>
      form.name.trim().length > 0 &&
      form.layers.every((l) => l.audio_file_id) &&
      (form.on_end.type !== "goto" || !!form.on_end.scene_id)
    );

    const save = async () => {
      if (!canSave.value) return;
      saving.value = true;
      const payload = {
        name: form.name.trim(),
        description: form.description.trim() || null,
        layers: form.layers,
        group_volumes: form.group_volumes,
        on_end: form.on_end,
      };
      const res = store.editingSceneId
        ? await API.updateScene(store.editingSceneId, payload)
        : await API.createScene(payload);
      saving.value = false;
      if (!(await reportFetch(res, "salvar cena"))) return;
      await refreshScenes();
      goto("scenes");
    };

    const otherScenes = computed(() =>
      store.scenes.filter((s) => s.id !== store.editingSceneId)
    );

    return {
      store, form, saving, isEditing,
      addLayer, removeLayer, onAudioFileChange, setLoopRegion,
      setOnEndType, save, goto, canSave, otherScenes,
    };
  },
  components: { LoopRegionEditor: markRaw(LoopRegionEditor) },
  template: `
    <div>
      <div class="header-actions">
        <div class="section-title" style="margin-bottom: 0;">
          {{ isEditing ? 'editar cena' : 'nova cena' }}
        </div>
        <button @click="goto('scenes')" style="background: transparent; border-color: var(--border);">cancelar</button>
      </div>

      <div class="form-field">
        <label>nome</label>
        <input type="text" v-model="form.name" placeholder="Floresta - Exploração" />
      </div>

      <div class="form-field">
        <label>descrição (opcional)</label>
        <textarea v-model="form.description" placeholder="Uma cena calma na floresta…"></textarea>
      </div>

      <div class="form-field">
        <label>ao encerrar (botão FIM DA CENA)</label>
        <select :value="form.on_end.type" @change="setOnEndType($event.target.value)">
          <option value="return_previous">↩ voltar para a cena anterior</option>
          <option value="goto">→ ir para uma cena específica</option>
          <option value="stop">⏹ parar tudo</option>
        </select>
      </div>

      <div v-if="form.on_end.type === 'goto'" class="form-field">
        <label>cena de destino</label>
        <select v-model="form.on_end.scene_id">
          <option v-for="s in otherScenes" :key="s.id" :value="s.id">{{ s.name }}</option>
        </select>
      </div>

      <div class="section-title" style="margin-top: 20px;">camadas ({{ form.layers.length }})</div>

      <div class="group-editor">
        <label v-for="group in ['music', 'ambience', 'sfx']" :key="group">
          {{ group === 'music' ? 'música' : group === 'ambience' ? 'ambiente' : 'SFX' }}
          <input type="range" min="0" max="1" step="0.01"
                 v-model.number="form.group_volumes[group]"
                 :aria-label="'Volume inicial do grupo ' + group" />
          {{ Math.round(form.group_volumes[group] * 100) }}%
        </label>
      </div>

      <div v-if="store.uploads.length === 0" class="empty-state">
        nenhum arquivo de áudio disponível —
        <a href="#" @click.prevent="goto('uploads')" style="color: var(--accent);">faça upload primeiro</a>
      </div>

      <div v-for="(layer, i) in form.layers" :key="i" class="layer-editor">
        <div class="layer-head">
          <h4>camada {{ i + 1 }}</h4>
          <button class="remove" @click="removeLayer(i)">remover</button>
        </div>
        <div class="form-field">
          <label>arquivo</label>
          <select :value="layer.audio_file_id" @change="onAudioFileChange(i, $event.target.value)">
            <option v-for="f in store.uploads" :key="f.id" :value="f.id">{{ f.original_name }}</option>
          </select>
        </div>
        <div class="form-field">
          <label>grupo</label>
          <select v-model="layer.group">
            <option value="music">música</option>
            <option value="ambience">ambiente</option>
            <option value="sfx">SFX</option>
          </select>
        </div>
        <div class="form-field">
          <label>
            <input type="range" min="0" max="1" step="0.01" v-model.number="layer.volume" />
            volume: {{ Math.round(layer.volume * 100) }}%
          </label>
        </div>
        <div class="form-field">
          <label>
            <input type="range" min="-1" max="1" step="0.01"
                   v-model.number="layer.pan_lr" :aria-label="'Pan da camada ' + (i + 1)" />
            pan: {{ layer.pan_lr > 0 ? '+' : '' }}{{ layer.pan_lr.toFixed(2) }}
          </label>
        </div>
        <div class="form-inline">
          <div class="form-field">
            <label>fade in (ms)</label>
            <input type="text" inputmode="numeric" v-model.number="layer.fade_in_ms" />
          </div>
          <div class="form-field">
            <label>fade out (ms)</label>
            <input type="text" inputmode="numeric" v-model.number="layer.fade_out_ms" />
          </div>
        </div>
        <label class="checkbox">
          <input type="checkbox" v-model="layer.loop" />
          loop (necessário para trilhas contínuas)
        </label>
        <LoopRegionEditor
          v-if="layer.audio_file_id"
          :key="layer.audio_file_id"
          :audio-file-id="layer.audio_file_id"
          :loop-start-ms="layer.loop_start_ms"
          :loop-end-ms="layer.loop_end_ms"
          @update="setLoopRegion(i, $event)"
        />
      </div>

      <button @click="addLayer" :disabled="store.uploads.length === 0"
              style="width: 100%; margin-top: 8px;">
        + adicionar camada
      </button>

      <div class="form-actions">
        <button @click="goto('scenes')" style="background: transparent;">cancelar</button>
        <button class="primary" :disabled="!canSave || saving" @click="save">
          {{ saving ? 'salvando…' : (isEditing ? 'salvar alterações' : 'criar cena') }}
        </button>
      </div>
    </div>
  `,
};

// ---- Root App ---------------------------------------------------------------

const App = {
  components: { ScenesView, UploadsView, EditorView },
  setup() {
    let disconnectWs = null;

    const localMaster = ref(1.0);
    watch(() => store.state.master_volume, (v) => {
      if (Math.abs(v - localMaster.value) > 0.01) localMaster.value = v;
    });
    const pushMaster = debounce(async (v) => {
      await reportFetch(await API.setVolume("master", v), "ajustar volume master");
    }, 100);
    watch(localMaster, (v) => pushMaster(v));

    const currentScene = computed(() =>
      store.scenes.find((s) => s.id === store.state.current_scene_id) || null
    );

    const stopAll = async () => { await reportFetch(await API.stop(), "parar reprodução"); };
    const endScene = async () => { await reportFetch(await API.endScene(), "encerrar cena"); };

    onMounted(async () => {
      disconnectWs = connectWebSocket();
      await Promise.all([refreshScenes(), refreshUploads()]);
      store.state = await API.initialState();
    });

    onBeforeUnmount(() => {
      if (disconnectWs) disconnectWs();
    });

    const logout = () => window.LoremasterAuth.logout();

    return { store, localMaster, currentScene, stopAll, endScene, goto, logout };
  },
  template: `
    <header>
      <h1>Loremaster</h1>
      <div style="display: flex; align-items: center; gap: 12px;">
        <a href="/map" style="color: var(--muted); font-size: 12px; text-decoration: none;">↗ mapa</a>
        <a href="/campaigns" style="color: var(--muted); font-size: 12px; text-decoration: none;">campanhas</a>
        <a href="/users" style="color: var(--muted); font-size: 12px; text-decoration: none;">jogadores</a>
        <button @click="logout" style="background: transparent;">sair</button>
        <div class="status-line">
          <span class="status-dot" :class="store.connected ? 'online' : 'offline'"></span>
          {{ store.connected ? 'conectado' : 'reconectando…' }}
          <span v-if="store.state.xrun_count > 0" style="color: var(--warning); margin-left: 8px;">
            xruns: {{ store.state.xrun_count }}
          </span>
        </div>
      </div>
    </header>

    <nav class="tabs">
      <button :class="{ active: store.view === 'scenes' }" @click="goto('scenes')">cenas</button>
      <button :class="{ active: store.view === 'uploads' }" @click="goto('uploads')">áudios</button>
      <button :class="{ active: store.view === 'editor' }" @click="goto('editor')">
        {{ store.editingSceneId ? 'editando…' : '+ cena' }}
      </button>
    </nav>

    <main>
      <div v-if="store.error" class="error-banner">
        <button @click="store.error = null">×</button>
        {{ store.error }}
      </div>
      <ScenesView v-if="store.view === 'scenes'" />
      <UploadsView v-else-if="store.view === 'uploads'" />
      <EditorView v-else-if="store.view === 'editor'" :key="store.editingSceneId || 'new'" />
    </main>

    <footer>
      <div class="master-volume">
        <span>master</span>
        <input type="range" min="0" max="1" step="0.01" v-model.number="localMaster"
               aria-label="Volume master" />
        <span>{{ Math.round(localMaster * 100) }}%</span>
      </div>
      <div class="footer-buttons">
        <button class="stop" :disabled="!currentScene" @click="stopAll">■ parar</button>
        <button class="end-scene" :disabled="!currentScene" @click="endScene">
          FIM DA CENA
        </button>
      </div>
    </footer>
  `,
};

createApp(App).mount("#app");
