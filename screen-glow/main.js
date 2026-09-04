const { app, BrowserWindow, screen } = require("electron");
const path = require("path");
const WebSocket = require("ws");

const WS_URL = process.env.JARVIS_WS_URL || "ws://localhost:8741/ws/glow";
const FADE_TIMEOUT_MS = parseInt(process.env.GLOW_TIMEOUT_MS || "6000", 10);

let windows = [];
let wsClient = null;
let reconnectTimer = null;

function createGlowWindows() {
  const displays = screen.getAllDisplays();
  for (const display of displays) {
    const { x, y, width, height } = display.bounds;
    const win = new BrowserWindow({
      x,
      y,
      width,
      height,
      transparent: true,
      frame: false,
      alwaysOnTop: true,
      skipTaskbar: true,
      hasShadow: false,
      resizable: false,
      focusable: false,
      show: false,
      webPreferences: {
        contextIsolation: true,
        preload: path.join(__dirname, "preload.js"),
      },
    });

    win.setIgnoreMouseEvents(true, { forward: true });
    if (process.platform === "darwin") {
      win.setVisibleOnAllWorkspaces(true, { visibleOnFullScreen: true });
    }
    win.setAlwaysOnTop(true, "screen-saver");

    win.loadFile("renderer.html");
    windows.push(win);
  }
}

function sendToAll(channel, data) {
  for (const win of windows) {
    if (!win.isDestroyed()) {
      win.webContents.send(channel, data);
    }
  }
}

function showGlow() {
  for (const win of windows) {
    if (!win.isDestroyed() && !win.isVisible()) {
      win.showInactive();
    }
  }
  sendToAll("glow", { action: "wake" });
}

function hideGlow() {
  sendToAll("glow", { action: "sleep" });
  setTimeout(() => {
    for (const win of windows) {
      if (!win.isDestroyed()) {
        win.hide();
      }
    }
  }, 800);
}

function connectWebSocket() {
  if (wsClient) {
    wsClient.removeAllListeners();
    wsClient.terminate();
  }

  wsClient = new WebSocket(WS_URL);

  wsClient.on("open", () => {
    console.log("[glow] Connected to JARVIS at", WS_URL);
  });

  wsClient.on("message", (data) => {
    try {
      const msg = JSON.parse(data.toString());
      if (msg.event === "wake" || msg.action === "wake") {
        showGlow();
      } else if (msg.event === "sleep" || msg.action === "sleep") {
        hideGlow();
      }
    } catch (err) {
      console.error("[glow] Bad message:", err.message);
    }
  });

  wsClient.on("close", () => {
    console.log("[glow] Disconnected, reconnecting in 3s...");
    scheduleReconnect();
  });

  wsClient.on("error", (err) => {
    console.error("[glow] WS error:", err.message);
  });
}

function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => {
    reconnectTimer = null;
    connectWebSocket();
  }, 3000);
}

app.whenReady().then(() => {
  createGlowWindows();
  connectWebSocket();
});

app.on("window-all-closed", () => {
  app.quit();
});
