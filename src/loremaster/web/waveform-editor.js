// Shared 3-region waveform editor (intro / loop / tail).
//
// Used by /map (SceneModal) and / (EditorView) to define loop markers on a
// layer's audio file. Loop markers are optional — a layer without them either
// loops the whole file or plays once (per LayerConfig.loop).
//
// Regions:
//   - intro:  [0, loop_start_ms)         — soft amber, non-interactive
//   - loop:   [loop_start_ms, loop_end_ms) — blue, draggable/resizable
//   - tail:   [loop_end_ms, duration)    — soft red, non-interactive
//
// The user only drags the loop region; intro/tail auto-follow.

import { defineComponent, ref, computed, onMounted, onBeforeUnmount } from "vue";
import WaveSurfer from "wavesurfer.js";
import RegionsPlugin from "wavesurfer.js/plugins/regions.esm.js";

const COLORS = {
  intro: "rgba(255, 200, 100, 0.18)",
  loop:  "rgba(88, 166, 255, 0.28)",
  tail:  "rgba(240, 108, 108, 0.18)",
};

export const LoopRegionEditor = defineComponent({
  name: "LoopRegionEditor",
  props: {
    audioFileId: { type: String, required: true },
    loopStartMs: { type: Number, default: null },
    loopEndMs:   { type: Number, default: null },
  },
  emits: ["update"],
  setup(props, { emit }) {
    const containerRef = ref(null);
    const isPlaying = ref(false);
    const isReady = ref(false);
    // Kept in raw JS closures — Vue reactivity fights wavesurfer's internal
    // mutations and causes "maximum recursive updates" errors otherwise.
    let ws = null;
    let regionsPlugin = null;
    let loopRegion = null;
    let introRegion = null;
    let tailRegion = null;

    const hasRegion = computed(
      () => props.loopStartMs != null && props.loopEndMs != null,
    );

    const emitUpdate = (startSec, endSec) => {
      emit("update", {
        loop_start_ms: Math.round(startSec * 1000),
        loop_end_ms:   Math.round(endSec * 1000),
      });
    };

    const syncIntroTail = (startSec, endSec) => {
      const dur = ws ? ws.getDuration() : 0;
      if (!dur) return;
      // Intro: only if there is material before loop.start
      if (startSec > 0.001) {
        if (introRegion) {
          introRegion.setOptions({ start: 0, end: startSec });
        } else {
          introRegion = regionsPlugin.addRegion({
            start: 0, end: startSec, color: COLORS.intro,
            drag: false, resize: false, content: "intro",
          });
        }
      } else if (introRegion) {
        introRegion.remove();
        introRegion = null;
      }
      // Tail: only if there is material after loop.end
      if (endSec < dur - 0.001) {
        if (tailRegion) {
          tailRegion.setOptions({ start: endSec, end: dur });
        } else {
          tailRegion = regionsPlugin.addRegion({
            start: endSec, end: dur, color: COLORS.tail,
            drag: false, resize: false, content: "tail",
          });
        }
      } else if (tailRegion) {
        tailRegion.remove();
        tailRegion = null;
      }
    };

    const attachLoop = (startSec, endSec) => {
      if (loopRegion) loopRegion.remove();
      loopRegion = regionsPlugin.addRegion({
        start: startSec, end: endSec, color: COLORS.loop,
        drag: true, resize: true, content: "loop",
      });
      // Live update of intro/tail while dragging (visual feedback).
      loopRegion.on("update", () => {
        syncIntroTail(loopRegion.start, loopRegion.end);
      });
      // Persist only when the drag finishes (avoid spamming the parent).
      loopRegion.on("update-end", () => {
        emitUpdate(loopRegion.start, loopRegion.end);
      });
      syncIntroTail(startSec, endSec);
    };

    const createDefaultRegion = () => {
      if (!ws || !isReady.value) return;
      const d = ws.getDuration();
      if (d <= 0) return;
      // Middle 60% of the file — a decent starting point.
      const start = d * 0.2;
      const end = d * 0.8;
      attachLoop(start, end);
      emitUpdate(start, end);
    };

    const clearRegion = () => {
      if (loopRegion)  { loopRegion.remove();  loopRegion = null; }
      if (introRegion) { introRegion.remove(); introRegion = null; }
      if (tailRegion)  { tailRegion.remove();  tailRegion = null; }
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
          attachLoop(props.loopStartMs / 1000, props.loopEndMs / 1000);
        }
      });
      ws.on("play",   () => (isPlaying.value = true));
      ws.on("pause",  () => (isPlaying.value = false));
      ws.on("finish", () => (isPlaying.value = false));
    });

    onBeforeUnmount(() => {
      if (ws) { try { ws.destroy(); } catch (_) {} ws = null; }
    });

    return {
      containerRef, isPlaying, isReady, hasRegion,
      togglePlay, createDefaultRegion, clearRegion,
    };
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
          arraste a faixa azul (loop). amarelo = intro, vermelho = tail.
        </span>
      </div>
    </div>
  `,
});
