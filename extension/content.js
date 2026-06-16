// Injected into every page. Renders the subtitle sidebar and handles TTS playback.

(function () {
  if (window.__autoTranslationLoaded) return;
  window.__autoTranslationLoaded = true;

  // ─── State ────────────────────────────────────────────────────────────────
  let sidebar = null;
  let sidebarBody = null;
  let collapsed = false;
  let userScrolledUp = false;
  let uiSettings = {};

  // ─── UI settings ──────────────────────────────────────────────────────────
  function refreshUISettings(callback) {
    chrome.runtime.sendMessage({ type: "get_ui_settings" }, (res) => {
      uiSettings = res?.settings || {};
      if (sidebar) applyUISettings();
      if (callback) callback();
    });
  }

  function applyUISettings() {
    if (sidebarBody) sidebarBody.style.fontSize = uiSettings.fontSize || "14px";
    const onRight = uiSettings.position === "right";
    if (sidebar) {
      sidebar.style.left  = onRight ? "auto" : "0";
      sidebar.style.right = onRight ? "0"    : "auto";
      sidebar.style.borderRight = onRight ? "none" : "1px solid rgba(255,255,255,0.12)";
      sidebar.style.borderLeft  = onRight ? "1px solid rgba(255,255,255,0.12)" : "none";
    }
  }

  // ─── Sidebar ──────────────────────────────────────────────────────────────
  const SIDEBAR_W = "290px";
  const COLLAPSED_W = "36px";

  function buildSidebar() {
    if (sidebar) return;

    sidebar = document.createElement("div");
    sidebar.id = "at-sidebar";
    Object.assign(sidebar.style, {
      position: "fixed",
      left: "0",
      top: "0",
      bottom: "0",
      width: SIDEBAR_W,
      zIndex: "2147483647",
      display: "flex",
      flexDirection: "column",
      background: "rgba(15,15,15,0.82)",
      backdropFilter: "blur(6px)",
      color: "#f0f0f0",
      fontFamily: "Arial, sans-serif",
      fontSize: uiSettings.fontSize || "14px",
      borderRight: "1px solid rgba(255,255,255,0.12)",
      transition: "width 0.15s ease",
      userSelect: "text",
      pointerEvents: "auto",
      overflow: "hidden",
      boxSizing: "border-box",
    });

    // Header row
    const header = document.createElement("div");
    Object.assign(header.style, {
      display: "flex",
      alignItems: "center",
      justifyContent: "space-between",
      padding: "7px 10px",
      borderBottom: "1px solid rgba(255,255,255,0.12)",
      flexShrink: "0",
      userSelect: "none",
      cursor: "default",
    });

    const title = document.createElement("span");
    title.id = "at-title";
    title.textContent = "AutoTranslation";
    Object.assign(title.style, {
      fontSize: "11px",
      fontWeight: "bold",
      color: "rgba(255,255,255,0.55)",
      letterSpacing: "0.05em",
      whiteSpace: "nowrap",
      overflow: "hidden",
    });

    const collapseBtn = document.createElement("button");
    collapseBtn.id = "at-collapse";
    collapseBtn.title = "Collapse panel";
    collapseBtn.textContent = "◀";
    Object.assign(collapseBtn.style, {
      background: "none",
      border: "none",
      color: "rgba(255,255,255,0.5)",
      cursor: "pointer",
      fontSize: "13px",
      padding: "0 2px",
      lineHeight: "1",
      flexShrink: "0",
    });
    collapseBtn.addEventListener("click", toggleCollapse);

    header.appendChild(title);
    header.appendChild(collapseBtn);

    // Scrollable subtitle body
    sidebarBody = document.createElement("div");
    sidebarBody.id = "at-body";
    Object.assign(sidebarBody.style, {
      flex: "1",
      overflowY: "auto",
      overflowX: "hidden",
      padding: "2px 0",
      fontSize: uiSettings.fontSize || "14px",
    });

    // Track whether the user has scrolled away from the bottom
    sidebarBody.addEventListener("scroll", () => {
      const gap = sidebarBody.scrollHeight - sidebarBody.scrollTop - sidebarBody.clientHeight;
      userScrolledUp = gap > 50;
    });

    sidebar.appendChild(header);
    sidebar.appendChild(sidebarBody);
    document.body.appendChild(sidebar);
    applyUISettings();
  }

  function toggleCollapse() {
    collapsed = !collapsed;
    const btn = document.getElementById("at-collapse");
    const ttl = document.getElementById("at-title");
    if (collapsed) {
      sidebar.style.width = COLLAPSED_W;
      if (ttl) ttl.style.display = "none";
      if (sidebarBody) sidebarBody.style.display = "none";
      if (btn) btn.textContent = "▶";
    } else {
      sidebar.style.width = SIDEBAR_W;
      if (ttl) ttl.style.display = "";
      if (sidebarBody) sidebarBody.style.display = "";
      if (btn) btn.textContent = "◀";
      // Scroll to bottom on expand
      if (sidebarBody && !userScrolledUp) {
        sidebarBody.scrollTop = sidebarBody.scrollHeight;
      }
    }
  }

  function showSubtitle(original, translation) {
    buildSidebar();

    const entry = document.createElement("div");
    Object.assign(entry.style, {
      padding: "6px 10px 8px",
      borderBottom: "1px solid rgba(255,255,255,0.07)",
      lineHeight: "1.5",
    });

    if (uiSettings.showOriginal && original) {
      const origEl = document.createElement("div");
      origEl.textContent = original;
      Object.assign(origEl.style, {
        color: "rgba(255,255,255,0.38)",
        fontSize: "0.82em",
        fontStyle: "italic",
        marginBottom: "3px",
      });
      entry.appendChild(origEl);
    }

    const transEl = document.createElement("div");
    transEl.textContent = translation;
    entry.appendChild(transEl);

    sidebarBody.appendChild(entry);

    if (!userScrolledUp) {
      sidebarBody.scrollTop = sidebarBody.scrollHeight;
    }
  }

  // ─── TTS audio (browser-side fallback) ────────────────────────────────────
  let audioCtx = null;
  let gainNode = null;
  let currentSource = null;
  let pendingTTSVolume = 100;
  let pendingAudioTask = null;
  let audioUnlocked = false;

  function getAudioCtx() {
    if (!audioCtx || audioCtx.state === "closed") {
      audioCtx = new AudioContext();
      gainNode = audioCtx.createGain();
      gainNode.gain.value = pendingTTSVolume / 100;
      gainNode.connect(audioCtx.destination);
    }
    return audioCtx;
  }

  function unlockAudioCtx() {
    if (audioUnlocked) return;
    const ctx = getAudioCtx();
    ctx.resume().then(() => {
      audioUnlocked = true;
      hideUnlockPrompt();
      if (pendingAudioTask) {
        const task = pendingAudioTask;
        pendingAudioTask = null;
        task();
      }
    }).catch(() => {});
  }
  document.addEventListener("click",       unlockAudioCtx, { capture: true, passive: true });
  document.addEventListener("keydown",     unlockAudioCtx, { capture: true, passive: true });
  document.addEventListener("pointerdown", unlockAudioCtx, { capture: true, passive: true });

  let unlockPrompt = null;
  function showUnlockPrompt() {
    if (unlockPrompt) return;
    unlockPrompt = document.createElement("div");
    unlockPrompt.textContent = "🔊 Click anywhere to enable voice";
    Object.assign(unlockPrompt.style, {
      position: "fixed", bottom: "110px", left: "50%", transform: "translateX(-50%)",
      background: "rgba(0,0,0,0.78)", color: "#fff", padding: "6px 16px",
      borderRadius: "20px", fontSize: "13px", fontFamily: "Arial,sans-serif",
      cursor: "pointer", zIndex: "2147483647", pointerEvents: "auto",
      border: "1px solid rgba(255,255,255,0.22)", backdropFilter: "blur(6px)",
    });
    unlockPrompt.addEventListener("click", unlockAudioCtx);
    document.body.appendChild(unlockPrompt);
    setTimeout(hideUnlockPrompt, 8000);
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

  // onStart callback is called right when audio playback begins — used to sync subtitle display.
  async function playAudioData(base64mp3, onStart) {
    const ctx = getAudioCtx();

    if (!audioUnlocked || ctx.state === "suspended") {
      pendingAudioTask = () => playAudioData(base64mp3, onStart);
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
      onStart?.();         // show subtitle exactly when voice starts
      source.start();
      currentSource = source;
      source.onended = () => { currentSource = null; };
    } catch (e) {
      console.warn("[AutoTranslation] audio playback error:", e);
      onStart?.();         // still show subtitle if audio fails
    }
  }

  document.addEventListener("pause", stopCurrentAudio, true);

  // ─── Volume control ────────────────────────────────────────────────────────
  let currentOriginalVolume = 1.0;
  let volumeEnforceInterval = null;

  function applyOriginalVolume() {
    document.querySelectorAll("audio, video").forEach((el) => {
      if (Math.abs(el.volume - currentOriginalVolume) > 0.01) el.volume = currentOriginalVolume;
    });
  }

  function setTTSVolume(pct) {
    pendingTTSVolume = pct;
    if (gainNode) gainNode.gain.value = pct / 100;
  }

  function setOriginalVolume(pct) {
    currentOriginalVolume = pct / 100;
    applyOriginalVolume();
    clearInterval(volumeEnforceInterval);
    if (pct < 100) volumeEnforceInterval = setInterval(applyOriginalVolume, 300);
  }

  chrome.storage.local.get(["originalVolume", "ttsVolume"], (res) => {
    setOriginalVolume(res.originalVolume ?? 100);
    setTTSVolume(res.ttsVolume ?? 100);
  });

  chrome.storage.onChanged.addListener((changes, area) => {
    if (area !== "local") return;
    if (changes.originalVolume) setOriginalVolume(changes.originalVolume.newValue);
    if (changes.ttsVolume)      setTTSVolume(changes.ttsVolume.newValue);
  });

  // ─── Messages ──────────────────────────────────────────────────────────────
  refreshUISettings();

  chrome.runtime.onMessage.addListener((msg) => {
    if (msg.type === "subtitle") {
      if (msg.audio) {
        // Browser-side TTS: show subtitle the instant audio starts playing (in sync).
        playAudioData(msg.audio, () => showSubtitle(msg.original, msg.translation));
      } else {
        // No browser audio (TTS off or service-side playback): show immediately.
        // The service already started playing via Python before sending this message.
        showSubtitle(msg.original, msg.translation);
      }
    }
    if (msg.type === "update_ui") {
      refreshUISettings();
    }
  });
})();
