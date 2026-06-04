// Preload de Electron — expone un puente mínimo y seguro al renderer.
// Con contextIsolation, el renderer solo ve `window.omniDesktop`.
const { contextBridge } = require('electron');

contextBridge.exposeInMainWorld('omniDesktop', {
  isElectron: true,
  platform: process.platform, // 'win32' | 'darwin' | 'linux'
});
