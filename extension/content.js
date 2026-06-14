// Injected into every page. Renders the subtitle overlay.

(function () {
  if (window.__autoTranslationLoaded) return;
  window.__autoTranslationLoaded = true;

  let overlay = null;
  let hideTimer = null;
  let uiSettings = {};

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
    const el = getOrCreateOverlay();
    applyUISettings(el);

    if (uiSettings.showOriginal) {
      el.innerHTML = `<span class="at-original">${escapeHtml(original)}</span><span class="at-translation">${escapeHtml(translation)}</span>`;
    } else {
      el.innerHTML = `<span class="at-translation">${escapeHtml(translation)}</span>`;
    }

    el.classList.add("at-visible");

    if (hideTimer) clearTimeout(hideTimer);
    const wordCount = translation.split(/\s+/).length;
    const duration = Math.min(Math.max(wordCount * 350, 3000), 8000);
    hideTimer = setTimeout(() => el.classList.remove("at-visible"), duration);
  }

  function escapeHtml(str) {
    return str
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  refreshUISettings();

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "subtitle") {
      showSubtitle(msg.original, msg.translation);
    }
    if (msg.type === "update_ui") {
      refreshUISettings(() => {
        if (overlay) applyUISettings(overlay);
      });
    }
  });
})();
