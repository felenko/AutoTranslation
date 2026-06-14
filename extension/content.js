// Injected into every page. Renders the subtitle overlay.

(function () {
  if (window.__autoTranslationLoaded) return;
  window.__autoTranslationLoaded = true;

  let overlay = null;
  let hideTimer = null;
  let uiSettings = {};
  const MAX_LINES = 2;
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
      const isLatest = i === subtitleBuffer.length - 1;
      const cls = isLatest ? "at-latest" : "at-prev";
      if (uiSettings.showOriginal && isLatest) {
        return `<div class="at-line ${cls}"><span class="at-original">${escapeHtml(entry.original)}</span>${escapeHtml(entry.translation)}</div>`;
      }
      return `<div class="at-line ${cls}">${escapeHtml(entry.translation)}</div>`;
    }).join("");

    el.classList.add("at-visible");

    if (hideTimer) clearTimeout(hideTimer);
    const wordCount = translation.split(/\s+/).length;
    const duration = Math.min(Math.max(wordCount * 350, 3000), 8000);
    hideTimer = setTimeout(() => {
      el.classList.remove("at-visible");
      subtitleBuffer = [];
    }, duration);
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  // --- TTS ---
  let ttsVoices = [];
  let lastSpoken = "";
  let ttsTimer = null;

  function loadVoices() {
    ttsVoices = window.speechSynthesis.getVoices();
  }
  loadVoices();
  window.speechSynthesis.addEventListener("voiceschanged", loadVoices);

  function pickVoice(gender) {
    const pool = ttsVoices.filter(v => v.lang.toLowerCase().startsWith("en"));
    const voices = pool.length ? pool : ttsVoices;
    if (gender === "male") {
      return voices.find(v => /\b(male|david|mark|james|guy|richard|george)\b/i.test(v.name)) || voices[0];
    }
    return voices.find(v => /\b(female|zira|susan|samantha|eva|linda|hazel)\b/i.test(v.name)) || voices[0];
  }

  function speakTranslation(text) {
    if (!uiSettings.ttsEnabled || !text) return;
    if (text === lastSpoken) return;   // don't repeat same phrase
    lastSpoken = text;

    if (ttsTimer) clearTimeout(ttsTimer);
    window.speechSynthesis.cancel();
    // Chrome needs a brief gap after cancel() before speak() or it loops
    ttsTimer = setTimeout(() => {
      const utter = new SpeechSynthesisUtterance(text);
      utter.rate = uiSettings.ttsRate || 1.0;
      utter.volume = 1.0;
      const voice = pickVoice(uiSettings.ttsVoice || "female");
      if (voice) utter.voice = voice;
      utter.onend = () => { lastSpoken = ""; };   // allow re-speaking after it finishes
      window.speechSynthesis.speak(utter);
    }, 100);
  }

  // Stop TTS when video pauses
  document.addEventListener("pause", () => {
    window.speechSynthesis.cancel();
    lastSpoken = "";
  }, true);
  document.addEventListener("play", () => {
    lastSpoken = "";
  }, true);

  refreshUISettings();

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "subtitle") {
      console.log("[AutoTranslation] subtitle received:", JSON.stringify(msg));
      showSubtitle(msg.original, msg.translation);
      speakTranslation(msg.translation);
    }
    if (msg.type === "update_ui") {
      refreshUISettings(() => {
        if (overlay) applyUISettings(overlay);
      });
    }
  });
})();
