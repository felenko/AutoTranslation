// Injected into every page. Renders the subtitle overlay.

(function () {
  if (window.__autoTranslationLoaded) return;
  window.__autoTranslationLoaded = true;

  let overlay = null;
  let hideTimer = null;
  let uiSettings = {};
  const MAX_LINES = 4;
  const LINE_OPACITY = [0.2, 0.4, 0.65, 1.0];   // oldest → newest
  const LINE_SIZE   = ["0.72em", "0.82em", "0.91em", "1em"];
  let subtitleBuffer = []; // [{original, translation}]

  function refreshUISettings(callback) {
    chrome.runtime.sendMessage({ type: "get_ui_settings" }, (res) => {
      uiSettings = res?.settings || {};
      if (callback) callback();
    });
  }

  function applyUISettings(el) {
    el.style.fontSize = uiSettings.fontSize || "22px";
    el.style.fontFamily = uiSettings.fontFamily || "Arial, sans-serif";
    el.style.color = uiSettings.color || "#ffffff";
    el.style.bottom = uiSettings.position === "top" ? "auto" : (uiSettings.bottom || "60px");
    el.style.top = uiSettings.position === "top" ? (uiSettings.top || "40px") : "auto";
  }

  function getOrCreateOverlay() {
    if (overlay) return overlay;

    overlay = document.createElement("div");
    overlay.id = "autotranslation-overlay";
    applyUISettings(overlay);
    document.body.appendChild(overlay);
    return overlay;
  }

  function showSubtitle(original, translation) {
    subtitleBuffer.push({ original, translation });
    if (subtitleBuffer.length > MAX_LINES) subtitleBuffer.shift();

    const el = getOrCreateOverlay();
    applyUISettings(el);

    el.innerHTML = subtitleBuffer.map((entry, i) => {
      const pos = i + (MAX_LINES - subtitleBuffer.length);  // align to bottom
      const opacity = LINE_OPACITY[pos] ?? 1.0;
      const size    = LINE_SIZE[pos]    ?? "1em";
      const isLatest = i === subtitleBuffer.length - 1;
      const inner = (uiSettings.showOriginal && isLatest)
        ? `<span class="at-original">${escapeHtml(entry.original)}</span>${escapeHtml(entry.translation)}`
        : escapeHtml(entry.translation);
      return `<div class="at-line" style="opacity:${opacity};font-size:${size}">${inner}</div>`;
    }).join("");

    el.classList.add("at-visible");

    if (hideTimer) clearTimeout(hideTimer);
    // Keep overlay visible for longer so rolled-up lines can be read
    hideTimer = setTimeout(() => {
      el.classList.remove("at-visible");
      subtitleBuffer = [];
    }, 12000);
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // --- Neural TTS (audio pre-generated server-side, arrives as base64 MP3) ---
  let audioCtx = null;
  let gainNode = null;
  let currentSource = null;
  let pendingTTSVolume = 100; // applied to gainNode when AudioContext is first created

  function getAudioCtx() {
    if (!audioCtx || audioCtx.state === "closed") {
      audioCtx = new AudioContext();
      gainNode = audioCtx.createGain();
      gainNode.gain.value = pendingTTSVolume / 100;
      gainNode.connect(audioCtx.destination);
    }
    return audioCtx;
  }

  // Unlock AudioContext on the first user gesture (Chrome autoplay policy).
  let audioUnlocked = false;
  let pendingAudio = null; // base64 string queued while context is locked

  function unlockAudioCtx() {
    if (audioUnlocked) return;
    const ctx = getAudioCtx();
    ctx.resume().then(() => {
      audioUnlocked = true;
      hideUnlockPrompt();
      if (pendingAudio) {
        const b64 = pendingAudio;
        pendingAudio = null;
        playAudioData(b64);
      }
    }).catch(() => {});
  }
  document.addEventListener("click",      unlockAudioCtx, { capture: true, passive: true });
  document.addEventListener("keydown",    unlockAudioCtx, { capture: true, passive: true });
  document.addEventListener("pointerdown",unlockAudioCtx, { capture: true, passive: true });

  // Visual prompt shown when TTS is available but AudioContext is blocked
  let unlockPrompt = null;
  function showUnlockPrompt() {
    if (unlockPrompt) return;
    const el = getOrCreateOverlay();
    unlockPrompt = document.createElement("div");
    unlockPrompt.id = "at-audio-unlock";
    unlockPrompt.textContent = "🔊 Click anywhere to enable voice";
    unlockPrompt.style.cssText = [
      "position:fixed", "bottom:110px", "left:50%", "transform:translateX(-50%)",
      "background:rgba(0,0,0,0.75)", "color:#fff", "padding:6px 16px",
      "border-radius:20px", "font-size:13px", "font-family:Arial,sans-serif",
      "cursor:pointer", "z-index:2147483647", "pointer-events:auto",
      "border:1px solid rgba(255,255,255,0.25)", "backdrop-filter:blur(6px)",
    ].join(";");
    unlockPrompt.addEventListener("click", unlockAudioCtx);
    document.body.appendChild(unlockPrompt);
    setTimeout(hideUnlockPrompt, 8000); // auto-dismiss after 8s
  }
  function hideUnlockPrompt() {
    if (unlockPrompt) { unlockPrompt.remove(); unlockPrompt = null; }
  }

  function stopCurrentAudio() {
    if (currentSource) {
      try { currentSource.stop(); } catch (_) {}
      currentSource = null;
    }
  }

  async function playAudioData(base64mp3) {
    const ctx = getAudioCtx();

    if (!audioUnlocked || ctx.state === "suspended") {
      pendingAudio = base64mp3; // keep only the most recent
      showUnlockPrompt();
      return;
    }

    try {
      const bytes = Uint8Array.from(atob(base64mp3), c => c.charCodeAt(0));
      const buffer = await ctx.decodeAudioData(bytes.buffer.slice(0));
      stopCurrentAudio();
      const source = ctx.createBufferSource();
      source.buffer = buffer;
      source.connect(gainNode);
      source.start();
      currentSource = source;
      source.onended = () => { currentSource = null; };
    } catch (e) {
      console.warn("[AutoTranslation] audio playback error:", e);
    }
  }

  // Stop audio when video pauses
  document.addEventListener("pause", stopCurrentAudio, true);

  // --- Volume control ---
  let currentOriginalVolume = 1.0;
  let volumeEnforceInterval = null;

  function applyOriginalVolume() {
    document.querySelectorAll("audio, video").forEach((el) => {
      if (Math.abs(el.volume - currentOriginalVolume) > 0.01) {
        el.volume = currentOriginalVolume;
      }
    });
  }

  function setTTSVolume(pct) {
    if (gainNode) gainNode.gain.value = pct / 100;
  }

  function setOriginalVolume(pct) {
    currentOriginalVolume = pct / 100;
    applyOriginalVolume();

    // Video players (YouTube etc.) re-apply their own volume after a few seconds.
    // Poll every 300ms to keep our value in effect when it's not 100%.
    clearInterval(volumeEnforceInterval);
    if (pct < 100) {
      volumeEnforceInterval = setInterval(applyOriginalVolume, 300);
    }
  }

  // Load persisted volumes and respond to live changes from the popup slider
  chrome.storage.local.get(["originalVolume", "ttsVolume"], (res) => {
    setOriginalVolume(res.originalVolume ?? 100);
    pendingTTSVolume = res.ttsVolume ?? 100;
    if (gainNode) gainNode.gain.value = pendingTTSVolume / 100;
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    if (changes.originalVolume) setOriginalVolume(changes.originalVolume.newValue);
    if (changes.ttsVolume) {
      pendingTTSVolume = changes.ttsVolume.newValue;
      if (gainNode) gainNode.gain.value = pendingTTSVolume / 100;
    }
  });

  refreshUISettings();

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "subtitle") {
      console.log("[AutoTranslation] subtitle received:", JSON.stringify({
        original: msg.original,
        translation: msg.translation,
        hasAudio: !!msg.audio,
        audioBytes: msg.audio ? Math.round(msg.audio.length * 0.75) : 0,
      }));
      showSubtitle(msg.original, msg.translation);
      if (msg.audio) {
        playAudioData(msg.audio);
      }
    }
    if (msg.type === "update_ui") {
      refreshUISettings(() => {
        if (overlay) applyUISettings(overlay);
      });
    }
  });
})();
