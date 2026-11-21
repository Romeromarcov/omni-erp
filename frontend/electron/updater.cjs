// Controlador modular y fail-safe de auto-actualización para Electron.
// Se desacopla mediante inyección de dependencias para permitir pruebas
// unitarias deterministas sin red ni binarios nativos de Electron.

const IPC_CHANNELS = Object.freeze({
  CHECK: 'updater:check',
  DOWNLOAD: 'updater:download',
  INSTALL: 'updater:install',
  STATUS: 'updater:status',
});

const UPDATER_DISABLED_MESSAGE = 'Auto-actualización deshabilitada en este entorno.';

const ERROR_MESSAGES = Object.freeze({
  NETWORK_ERROR: 'No se pudo conectar con el servidor de actualizaciones.',
  SIGNATURE_ERROR: 'La actualización no pudo verificarse de forma segura.',
  UNAVAILABLE: 'No hay actualizaciones disponibles en este momento.',
  UPDATER_ERROR: 'No se pudo completar la operación de actualización.',
});

/**
 * Normaliza cualquier error del updater a un código y mensaje seguro
 * sin exponer stack traces, rutas locales ni URLs internas al renderer.
 *
 * @param {unknown} err
 * @returns {{ code: keyof typeof ERROR_MESSAGES, message: string }}
 */
function sanitizeUpdaterError(err) {
  let raw = '';
  if (typeof err === 'string') {
    raw = err;
  } else if (err && typeof err === 'object' && 'message' in err && typeof err.message === 'string') {
    raw = err.message;
  }
  const normalized = raw.toLowerCase();

  if (
    normalized.includes('signature') ||
    normalized.includes('signed') ||
    normalized.includes('certificate') ||
    normalized.includes('authenticode') ||
    normalized.includes('checksum') ||
    normalized.includes('sha512') ||
    normalized.includes('publisher')
  ) {
    return { code: 'SIGNATURE_ERROR', message: ERROR_MESSAGES.SIGNATURE_ERROR };
  }

  if (
    normalized.includes('enotfound') ||
    normalized.includes('econnrefused') ||
    normalized.includes('etimedout') ||
    normalized.includes('econnreset') ||
    normalized.includes('eai_again') ||
    normalized.includes('err_internet_disconnected') ||
    normalized.includes('err_name_not_resolved') ||
    normalized.includes('net::err') ||
    normalized.includes('network') ||
    normalized.includes('timeout')
  ) {
    return { code: 'NETWORK_ERROR', message: ERROR_MESSAGES.NETWORK_ERROR };
  }

  if (
    normalized.includes('404') ||
    normalized.includes('enoent') ||
    normalized.includes('app-update.yml') ||
    normalized.includes('no published versions') ||
    normalized.includes('cannot find latest') ||
    normalized.includes('unable to find latest')
  ) {
    return { code: 'UNAVAILABLE', message: ERROR_MESSAGES.UNAVAILABLE };
  }

  return { code: 'UPDATER_ERROR', message: ERROR_MESSAGES.UPDATER_ERROR };
}

/**
 * @param {unknown} value
 * @returns {string | undefined}
 */
function sanitizeShortString(value) {
  if (typeof value !== 'string') return undefined;
  const trimmed = value.trim();
  if (!trimmed || trimmed.length > 64) return undefined;
  // Descartar posibles rutas, URLs o saltos de línea inesperados.
  if (/\s/.test(trimmed) || trimmed.includes('://') || trimmed.includes('\\') || trimmed.includes('/')) {
    return undefined;
  }
  return trimmed;
}

/**
 * @param {unknown} value
 * @returns {number}
 */
function toNonNegativeNumber(value) {
  return typeof value === 'number' && Number.isFinite(value) && value >= 0 ? value : 0;
}

/**
 * @param {unknown} value
 * @returns {number}
 */
function clampPercent(value) {
  const num = toNonNegativeNumber(value);
  return Math.min(100, Math.round(num * 100) / 100);
}

/**
 * @param {{ app?: { isPackaged?: boolean } | null, env?: Record<string, string | undefined> | null }} opts
 * @returns {boolean}
 */
function isUpdaterEnabled(opts = {}) {
  const { app, env } = opts;
  const isPackaged = Boolean(app && app.isPackaged === true);
  const disabledFlag = env && env.OMNI_DISABLE_AUTO_UPDATE === '1';
  return isPackaged && !disabledFlag;
}

/**
 * Carga lazy de electron únicamente cuando no se inyectaron dependencias.
 * @returns {{ app?: unknown, ipcMain?: unknown }}
 */
function resolveDefaultElectron() {
  try {
    return require('electron');
  } catch {
    return {};
  }
}

/**
 * Carga lazy de electron-updater únicamente cuando el updater está habilitado.
 * @returns {unknown}
 */
function resolveDefaultAutoUpdater() {
  try {
    const mod = require('electron-updater');
    return mod ? mod.autoUpdater : null;
  } catch {
    return null;
  }
}

/**
 * Crea un controlador desacoplado de auto-update para el proceso principal.
 *
 * @param {{
 *   autoUpdater?: any,
 *   app?: any,
 *   ipcMain?: any,
 *   getWindow?: () => any,
 *   env?: Record<string, string | undefined>,
 *   autoDownload?: boolean,
 *   logger?: { warn?: (...args: any[]) => void } | null,
 * }} [deps]
 */
function createUpdaterController(deps = {}) {
  const env = deps.env ?? process.env;
  const getWindow = typeof deps.getWindow === 'function' ? deps.getWindow : () => null;
  const autoDownload = Boolean(deps.autoDownload);
  const logger = deps.logger === undefined ? null : deps.logger;

  let resolvedElectron = null;
  function getElectron() {
    if (!resolvedElectron) {
      resolvedElectron = resolveDefaultElectron();
    }
    return resolvedElectron;
  }

  const app = deps.app !== undefined ? deps.app : getElectron().app;
  const ipcMain = deps.ipcMain !== undefined ? deps.ipcMain : getElectron().ipcMain;

  let updaterInstance = deps.autoUpdater ?? null;
  let initialized = false;
  let hasUpdateAvailable = false;
  let hasDownloadedUpdate = false;
  let currentStatus = 'idle';
  let currentVersion;
  let checkingPromise = null;
  let downloadPromise = null;
  let lastErrorInOperation = null;

  /** @type {Array<{ event: string, listener: (...args: any[]) => void }>} */
  const boundListeners = [];
  /** @type {string[]} */
  const registeredChannels = [];

  function logWarn(code) {
    if (logger && typeof logger.warn === 'function') {
      logger.warn('[omni-updater]', code);
    }
  }

  function isEnabled() {
    return isUpdaterEnabled({ app, env });
  }

  function sendStatus(payload) {
    currentStatus = payload.status;
    const win = getWindow();
    if (!win || (typeof win.isDestroyed === 'function' && win.isDestroyed())) {
      return false;
    }
    const wc = win.webContents;
    if (!wc || (typeof wc.isDestroyed === 'function' && wc.isDestroyed()) || typeof wc.send !== 'function') {
      return false;
    }
    try {
      wc.send(IPC_CHANNELS.STATUS, payload);
      return true;
    } catch {
      return false;
    }
  }

  function isAuthorizedIpcEvent(event) {
    if (!event) return true;
    const win = getWindow();
    if (event.sender && win && win.webContents && event.sender !== win.webContents) {
      return false;
    }
    const frameUrl = event.senderFrame && typeof event.senderFrame.url === 'string' ? event.senderFrame.url : '';
    if (frameUrl && isEnabled() && !frameUrl.startsWith('app://omni')) {
      return false;
    }
    return true;
  }

  function handleUpdaterError(err) {
    const safe = sanitizeUpdaterError(err);
    lastErrorInOperation = safe;
    logWarn(safe.code);
    sendStatus({
      status: 'error',
      error: safe.message,
      errorCode: safe.code,
    });
    return safe;
  }

  function attachUpdaterListeners(updater) {
    const add = (event, listener) => {
      if (typeof updater.on === 'function') {
        updater.on(event, listener);
        boundListeners.push({ event, listener });
      }
    };

    add('checking-for-update', () => {
      lastErrorInOperation = null;
      sendStatus({ status: 'checking' });
    });

    add('update-available', (info) => {
      hasUpdateAvailable = true;
      hasDownloadedUpdate = false;
      currentVersion = sanitizeShortString(info && info.version);
      sendStatus({
        status: 'available',
        version: currentVersion,
        releaseDate: sanitizeShortString(info && info.releaseDate),
      });
    });

    add('update-not-available', (info) => {
      hasUpdateAvailable = false;
      hasDownloadedUpdate = false;
      currentVersion = sanitizeShortString(info && info.version);
      sendStatus({
        status: 'not-available',
        version: currentVersion,
      });
    });

    add('download-progress', (progress) => {
      sendStatus({
        status: 'downloading',
        progress: {
          percent: clampPercent(progress && progress.percent),
          bytesPerSecond: toNonNegativeNumber(progress && progress.bytesPerSecond),
          transferred: toNonNegativeNumber(progress && progress.transferred),
          total: toNonNegativeNumber(progress && progress.total),
        },
      });
    });

    add('update-downloaded', (info) => {
      hasUpdateAvailable = true;
      hasDownloadedUpdate = true;
      currentVersion = sanitizeShortString(info && info.version) ?? currentVersion;
      sendStatus({
        status: 'downloaded',
        version: currentVersion,
        releaseDate: sanitizeShortString(info && info.releaseDate),
      });
    });

    add('error', (err) => {
      handleUpdaterError(err);
    });
  }

  function registerIpcHandler(channel, handler) {
    if (!ipcMain || typeof ipcMain.handle !== 'function') return;
    if (typeof ipcMain.removeHandler === 'function') {
      try {
        ipcMain.removeHandler(channel);
      } catch {
        // Ignora si no había handler previo.
      }
    }
    ipcMain.handle(channel, async (event) => {
      if (!isAuthorizedIpcEvent(event)) {
        return {
          ok: false,
          status: 'error',
          error: ERROR_MESSAGES.UPDATER_ERROR,
          errorCode: 'UPDATER_ERROR',
        };
      }
      return handler();
    });
    registeredChannels.push(channel);
  }

  async function checkForUpdates() {
    if (!isEnabled() || !updaterInstance) {
      return {
        ok: false,
        status: 'disabled',
        error: UPDATER_DISABLED_MESSAGE,
      };
    }

    if (checkingPromise) {
      return checkingPromise;
    }

    checkingPromise = (async () => {
      lastErrorInOperation = null;
      try {
        const result = await updaterInstance.checkForUpdates();
        if (lastErrorInOperation) {
          return {
            ok: false,
            status: 'error',
            error: lastErrorInOperation.message,
            errorCode: lastErrorInOperation.code,
          };
        }
        const version = sanitizeShortString(result && result.updateInfo && result.updateInfo.version) ?? currentVersion;
        return {
          ok: true,
          status: currentStatus,
          version,
        };
      } catch (err) {
        const safe = lastErrorInOperation ?? handleUpdaterError(err);
        return {
          ok: false,
          status: 'error',
          error: safe.message,
          errorCode: safe.code,
        };
      } finally {
        checkingPromise = null;
      }
    })();

    return checkingPromise;
  }

  async function downloadUpdate() {
    if (!isEnabled() || !updaterInstance) {
      return {
        ok: false,
        status: 'disabled',
        error: UPDATER_DISABLED_MESSAGE,
      };
    }

    if (hasDownloadedUpdate) {
      return {
        ok: true,
        status: 'downloaded',
        version: currentVersion,
      };
    }

    if (!hasUpdateAvailable) {
      return {
        ok: false,
        status: currentStatus,
        error: 'No hay una actualización disponible para descargar.',
      };
    }

    if (downloadPromise) {
      return downloadPromise;
    }

    downloadPromise = (async () => {
      lastErrorInOperation = null;
      try {
        await updaterInstance.downloadUpdate();
        if (lastErrorInOperation) {
          return {
            ok: false,
            status: 'error',
            error: lastErrorInOperation.message,
            errorCode: lastErrorInOperation.code,
          };
        }
        return {
          ok: true,
          status: currentStatus,
          version: currentVersion,
        };
      } catch (err) {
        const safe = lastErrorInOperation ?? handleUpdaterError(err);
        return {
          ok: false,
          status: 'error',
          error: safe.message,
          errorCode: safe.code,
        };
      } finally {
        downloadPromise = null;
      }
    })();

    return downloadPromise;
  }

  function installUpdate() {
    if (!isEnabled() || !updaterInstance) {
      return {
        ok: false,
        status: 'disabled',
        error: UPDATER_DISABLED_MESSAGE,
      };
    }

    if (!hasDownloadedUpdate) {
      return {
        ok: false,
        status: currentStatus,
        error: 'No hay ninguna actualización descargada lista para instalar.',
      };
    }

    try {
      sendStatus({
        status: 'installing',
        version: currentVersion,
      });
      updaterInstance.quitAndInstall();
      return {
        ok: true,
        status: 'installing',
        version: currentVersion,
      };
    } catch (err) {
      const safe = handleUpdaterError(err);
      return {
        ok: false,
        status: 'error',
        error: safe.message,
        errorCode: safe.code,
      };
    }
  }

  function init() {
    if (initialized) {
      return { enabled: isEnabled() };
    }
    initialized = true;

    registerIpcHandler(IPC_CHANNELS.CHECK, checkForUpdates);
    registerIpcHandler(IPC_CHANNELS.DOWNLOAD, downloadUpdate);
    registerIpcHandler(IPC_CHANNELS.INSTALL, installUpdate);

    if (!isEnabled()) {
      currentStatus = 'disabled';
      return { enabled: false };
    }

    if (!updaterInstance) {
      updaterInstance = resolveDefaultAutoUpdater();
    }

    if (!updaterInstance) {
      currentStatus = 'disabled';
      return { enabled: false };
    }

    try {
      updaterInstance.autoDownload = autoDownload;
      if ('logger' in updaterInstance && deps.logger !== undefined) {
        updaterInstance.logger = deps.logger;
      }
      attachUpdaterListeners(updaterInstance);
      return { enabled: true };
    } catch (err) {
      handleUpdaterError(err);
      return { enabled: false };
    }
  }

  function cleanup() {
    if (updaterInstance) {
      for (const { event, listener } of boundListeners) {
        if (typeof updaterInstance.removeListener === 'function') {
          updaterInstance.removeListener(event, listener);
        } else if (typeof updaterInstance.off === 'function') {
          updaterInstance.off(event, listener);
        }
      }
    }
    boundListeners.length = 0;

    if (ipcMain && typeof ipcMain.removeHandler === 'function') {
      for (const channel of registeredChannels) {
        try {
          ipcMain.removeHandler(channel);
        } catch {
          // Ignora errores de limpieza en teardown.
        }
      }
    }
    registeredChannels.length = 0;

    initialized = false;
    hasUpdateAvailable = false;
    hasDownloadedUpdate = false;
    checkingPromise = null;
    downloadPromise = null;
    lastErrorInOperation = null;
    currentStatus = 'idle';
    currentVersion = undefined;
  }

  function getState() {
    return {
      enabled: isEnabled(),
      initialized,
      status: currentStatus,
      version: currentVersion,
      hasUpdateAvailable,
      hasDownloadedUpdate,
    };
  }

  return {
    init,
    cleanup,
    checkForUpdates,
    downloadUpdate,
    installUpdate,
    isEnabled,
    getState,
  };
}

module.exports = {
  IPC_CHANNELS,
  UPDATER_DISABLED_MESSAGE,
  ERROR_MESSAGES,
  sanitizeUpdaterError,
  isUpdaterEnabled,
  createUpdaterController,
};
