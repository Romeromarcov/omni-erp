// Preload de Electron — expone un puente mínimo y seguro al renderer.
// Con contextIsolation, el renderer solo ve `window.omniDesktop` y `window.omniUpdater`.

const UPDATER_CHANNELS = Object.freeze({
  CHECK: 'updater:check',
  DOWNLOAD: 'updater:download',
  INSTALL: 'updater:install',
  STATUS: 'updater:status',
});

/**
 * Registra los puentes seguros sobre contextBridge.
 * Extraído para permitir pruebas unitarias deterministas de la superficie expuesta.
 *
 * @param {{ exposeInMainWorld: (key: string, api: unknown) => void }} contextBridge
 * @param {{
 *   invoke: (channel: string) => Promise<unknown>,
 *   on: (channel: string, listener: (...args: any[]) => void) => void,
 *   off?: (channel: string, listener: (...args: any[]) => void) => void,
 *   removeListener?: (channel: string, listener: (...args: any[]) => void) => void,
 * }} ipcRenderer
 * @param {string} [platform]
 */
function exposePreloadBridges(contextBridge, ipcRenderer, platform = process.platform) {
  contextBridge.exposeInMainWorld('omniDesktop', {
    isElectron: true,
    platform, // 'win32' | 'darwin' | 'linux'
  });

  contextBridge.exposeInMainWorld('omniUpdater', {
    checkForUpdates: () => ipcRenderer.invoke(UPDATER_CHANNELS.CHECK),
    downloadUpdate: () => ipcRenderer.invoke(UPDATER_CHANNELS.DOWNLOAD),
    installUpdate: () => ipcRenderer.invoke(UPDATER_CHANNELS.INSTALL),
    onStatus: (listener) => {
      if (typeof listener !== 'function') {
        return () => {};
      }
      // Nunca propagar el objeto `event` interno de Electron al renderer.
      const wrapped = (_event, payload) => {
        listener(payload);
      };
      ipcRenderer.on(UPDATER_CHANNELS.STATUS, wrapped);
      return () => {
        if (typeof ipcRenderer.off === 'function') {
          ipcRenderer.off(UPDATER_CHANNELS.STATUS, wrapped);
        } else if (typeof ipcRenderer.removeListener === 'function') {
          ipcRenderer.removeListener(UPDATER_CHANNELS.STATUS, wrapped);
        }
      };
    },
  });
}

const electronApi = require('electron');
if (
  electronApi &&
  typeof electronApi === 'object' &&
  electronApi.contextBridge &&
  electronApi.ipcRenderer
) {
  exposePreloadBridges(electronApi.contextBridge, electronApi.ipcRenderer);
}

module.exports = {
  UPDATER_CHANNELS,
  exposePreloadBridges,
};
