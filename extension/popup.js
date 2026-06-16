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
  if (uiPrefs.position) $("position").value = uiPrefs.position;
  if (uiPrefs.showOriginal) $("show-original").checked = true;
});

$("tts-rate").addEventListener("input", () => {
  $("tts-rate-label").textContent = parseFloat($("tts-rate").value).toFixed(1) + "x";
});

$("chunk-duration").addEventListener("input", () => {
  $("chunk-label").textContent = parseFloat($("chunk-duration").value).toFixed(1) + "s";
});

// --- Volume sliders (live, stored locally — no server round-trip needed) ---
chrome.storage.local.get(["originalVolume", "ttsVolume"], (res) => {
  const ov = res.originalVolume ?? 100;
  const tv = res.ttsVolume ?? 100;
  $("orig-volume").value = ov;
  $("orig-vol-label").textContent = ov + "%";
  $("tts-volume").value = tv;
  $("tts-vol-label").textContent = tv + "%";
});

$("orig-volume").addEventListener("input", () => {
  const val = parseInt($("orig-volume").value);
  $("orig-vol-label").textContent = val + "%";
  chrome.storage.local.set({ originalVolume: val });
});

$("tts-volume").addEventListener("input", () => {
  const val = parseInt($("tts-volume").value);
  $("tts-vol-label").textContent = val + "%";
  chrome.storage.local.set({ ttsVolume: val });
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
