const { contextBridge, ipcRenderer } = require("electron");

contextBridge.exposeInMainWorld("glowAPI", {
  onGlow: (callback) => ipcRenderer.on("glow", (_event, data) => callback(data)),
});
