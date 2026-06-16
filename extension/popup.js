const $ = (id) => document.getElementById(id);

function populateDeviceSelect(id, devices, selected) {
  const el = $(id);
  const defaultOpt = el.options[0];
  el.innerHTML = "";
  el.appendChild(defaultOpt);
  for (const name of (devices || [])) {
    const opt = document.createElement("option");
    opt.value = name;
    opt.textContent = name;
    el.appendChild(opt);
  }
  if (selected) el.value = selected;
}

function applyConfig(c) {
  if (!c) return;
  if (c.stt_engine) $("stt-engine").value = c.stt_engine;
  if (c.translation_enabled !== undefined) $("translation-enabled").checked = !!c.translation_enabled;
  if (c.translation_engine) $("translation-engine").value = c.translation_engine;
  if (c.chunk_duration) { $("chunk-duration").value = c.chunk_duration; $("chunk-label").textContent = parseFloat(c.chunk_duration).toFixed(1) + "s"; }
  if (c.source_language !== undefined) $("source-language").value = c.source_language || "";
  if (c.target_language) $("target-language").value = c.target_language;
  if (c.ollama_model) $("ollama-model").value = c.ollama_model;
  if (c.cursor_model && $("cursor-model")) $("cursor-model").value = c.cursor_model;
  if (c.claude_model) $("claude-model").value = c.claude_model;
  if (c.tts_enabled !== undefined) $("tts-enabled").checked = !!c.tts_enabled;
  if (c.tts_voice_gender) $("tts-voice").value = c.tts_voice_gender;
  if (c.tts_rate !== undefined) {
    $("tts-rate").value = c.tts_rate;
    $("tts-rate-label").textContent = parseFloat(c.tts_rate).toFixed(1) + "x";
  }
  if (c.original_volume !== undefined) {
    const pct = Math.round(c.original_volume * 100);
    $("orig-volume").value = pct;
    $("orig-vol-label").textContent = pct + "%";
  }
  if (c.tts_volume !== undefined) {
    const pct = Math.round(c.tts_volume * 100);
    $("tts-volume").value = pct;
    $("tts-vol-label").textContent = pct + "%";
  }
  populateDeviceSelect("capture-device", c.loopback_devices, c.capture_device);
  populateDeviceSelect("playback-device", c.output_devices, c.tts_playback_device);
  toggleEngineSections();
}

function setStatus(status) {
  const connected = status === "connected";
  $("status-dot").className = `dot ${connected ? "connected" : "disconnected"}`;
}

// --- Init ---
chrome.runtime.sendMessage({ type: "get_status" }, (res) => {
  if (res) {
    setStatus(res.connected ? "connected" : "disconnected");
    $("toggle-subtitles").checked = res.subtitlesEnabled;
  }
});

chrome.runtime.sendMessage({ type: "get_config" }, (res) => {
  applyConfig(res?.config);
});

chrome.runtime.sendMessage({ type: "get_ui_settings" }, (res) => {
  const uiPrefs = res?.settings || {};
  if (uiPrefs.fontSize) $("font-size").value = uiPrefs.fontSize.replace("px", "");
  // Migrate old bottom/top values to left/right
  const pos = uiPrefs.position;
  if (pos) $("position").value = (pos === "top") ? "right" : (pos === "bottom") ? "left" : pos;
  if (uiPrefs.showOriginal) $("show-original").checked = true;
});

$("tts-rate").addEventListener("input", () => {
  $("tts-rate-label").textContent = parseFloat($("tts-rate").value).toFixed(1) + "x";
});

$("chunk-duration").addEventListener("input", () => {
  $("chunk-label").textContent = parseFloat($("chunk-duration").value).toFixed(1) + "s";
});

// --- Volume sliders ---
// Initial values come from server config (applyConfig above) but fall back to local storage.
chrome.storage.local.get(["originalVolume", "ttsVolume"], (res) => {
  // Only apply local storage values if the server hasn't already populated the sliders.
  if ($("orig-volume").value === "100" && res.originalVolume !== undefined) {
    $("orig-volume").value = res.originalVolume;
    $("orig-vol-label").textContent = res.originalVolume + "%";
  }
  if ($("tts-volume").value === "100" && res.ttsVolume !== undefined) {
    $("tts-volume").value = res.ttsVolume;
    $("tts-vol-label").textContent = res.ttsVolume + "%";
  }
});

$("orig-volume").addEventListener("input", () => {
  const val = parseInt($("orig-volume").value);
  $("orig-vol-label").textContent = val + "%";
  chrome.storage.local.set({ originalVolume: val });
  // Live update: service uses this for passthrough volume.
  chrome.runtime.sendMessage({ type: "update_config", config: { original_volume: val / 100 } });
});

$("tts-volume").addEventListener("input", () => {
  const val = parseInt($("tts-volume").value);
  $("tts-vol-label").textContent = val + "%";
  chrome.storage.local.set({ ttsVolume: val });
  // Live update: service uses this for output-device TTS volume.
  chrome.runtime.sendMessage({ type: "update_config", config: { tts_volume: val / 100 } });
});

// Live updates from the service (config push, connection status)
chrome.runtime.onMessage.addListener((msg) => {
  if (msg.type === "config") {
    applyConfig(msg.config);
  }
  if (msg.type === "status") {
    setStatus(msg.status);
  }
});

function toggleEngineSections() {
  const engine = $("translation-engine").value;
  $("ollama-section").style.display = engine === "ollama" ? "block" : "none";
  $("cursor-section").style.display = engine === "cursor" ? "block" : "none";
  $("claude-section").style.display = engine === "claude" ? "block" : "none";
}
$("translation-engine").addEventListener("change", toggleEngineSections);
toggleEngineSections();

$("toggle-subtitles").addEventListener("change", (e) => {
  chrome.runtime.sendMessage({ type: "toggle_subtitles", enabled: e.target.checked });
});

$("save-btn").addEventListener("click", () => {
  const configPatch = {
    stt_engine: $("stt-engine").value,
    translation_enabled: $("translation-enabled").checked,
    translation_engine: $("translation-engine").value,
    chunk_duration: parseFloat($("chunk-duration").value),
    source_language: $("source-language").value.trim(),
    target_language: $("target-language").value.trim() || "English",
    ollama_model: $("ollama-model").value.trim() || "llama3",
    cursor_model: ($("cursor-model")?.value ?? "").trim() || "claude-3-5-sonnet",
    claude_model: $("claude-model").value.trim() || "claude-sonnet-4-6",
    tts_enabled: $("tts-enabled").checked,
    tts_voice_gender: $("tts-voice").value,
    tts_rate: parseFloat($("tts-rate").value),
    capture_device: $("capture-device").value,
    tts_playback_device: $("playback-device").value,
    original_volume: parseInt($("orig-volume").value) / 100,
    tts_volume: parseInt($("tts-volume").value) / 100,
  };

  const uiPrefs = {
    fontSize: $("font-size").value + "px",
    position: $("position").value,
    showOriginal: $("show-original").checked,
  };

  chrome.runtime.sendMessage({ type: "set_ui_settings", settings: uiPrefs });

  chrome.runtime.sendMessage({ type: "update_config", config: configPatch }, (res) => {
    const btn = $("save-btn");
    if (chrome.runtime.lastError || !res?.ok) {
      btn.textContent = res?.error || "Not connected!";
      btn.style.color = "#e55";
    } else {
      btn.textContent = "Saved!";
      btn.style.color = "";
    }
    setTimeout(() => {
      btn.textContent = "Apply settings";
      btn.style.color = "";
    }, 2000);
  });
});
