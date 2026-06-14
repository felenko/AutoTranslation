// Service worker: manages WebSocket connection to the local translation service
// and fans out subtitle messages to all active content scripts.

const WS_URL = "ws://localhost:8765";
const RECONNECT_DELAY_MS = 3000;

let ws = null;
let subtitlesEnabled = true;
let cachedConfig = null;

function connect() {
  ws = new WebSocket(WS_URL);

  ws.onopen = () => {
    console.log("[AutoTranslation] connected to service");
    broadcastToTabs({ type: "status", status: "connected" });
    notifyPopup({ type: "status", status: "connected" });
  };

  ws.onmessage = (event) => {
    let msg;
    try {
      msg = JSON.parse(event.data);
    } catch {
      return;
    }

    if (msg.type === "subtitle" && subtitlesEnabled) {
      broadcastToTabs(msg);
    } else if (msg.type === "config") {
      cachedConfig = msg.config;
      broadcastToTabs(msg);
      notifyPopup(msg);
    } else if (msg.type === "status") {
      broadcastToTabs(msg);
      notifyPopup(msg);
    }
  };

  ws.onclose = () => {
    console.log("[AutoTranslation] disconnected, reconnecting...");
    broadcastToTabs({ type: "status", status: "disconnected" });
    notifyPopup({ type: "status", status: "disconnected" });
    setTimeout(connect, RECONNECT_DELAY_MS);
  };

  ws.onerror = (err) => {
    console.error("[AutoTranslation] WS error", err);
  };
}

function broadcastToTabs(msg) {
  chrome.tabs.query({}, (tabs) => {
    for (const tab of tabs) {
      if (tab.id != null) {
        chrome.tabs.sendMessage(tab.id, msg).catch(() => {});
      }
    }
  });
}

function notifyPopup(msg) {
  chrome.runtime.sendMessage(msg).catch(() => {});
}

// Messages from popup or content scripts
chrome.runtime.onMessage.addListener((msg, _sender, sendResponse) => {
  if (msg.type === "toggle_subtitles") {
    subtitlesEnabled = msg.enabled;
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "update_config") {
    if (ws?.readyState !== WebSocket.OPEN) {
      sendResponse({ ok: false, error: "Service not connected. Is run.py running?" });
      return true;
    }
    ws.send(JSON.stringify(msg));
    sendResponse({ ok: true });
    return true;
  }

  if (msg.type === "get_config") {
    sendResponse({ config: cachedConfig });
    return true;
  }

  if (msg.type === "get_status") {
    sendResponse({
      connected: ws?.readyState === WebSocket.OPEN,
      subtitlesEnabled,
    });
    return true;
  }

  if (msg.type === "get_ui_settings") {
    chrome.storage.local.get(["autotranslation_ui"], (result) => {
      sendResponse({ settings: result.autotranslation_ui || {} });
    });
    return true;
  }

  if (msg.type === "set_ui_settings") {
    chrome.storage.local.set({ autotranslation_ui: msg.settings }, () => {
      broadcastToTabs({ type: "update_ui" });
      sendResponse({ ok: true });
    });
    return true;
  }
});

connect();
