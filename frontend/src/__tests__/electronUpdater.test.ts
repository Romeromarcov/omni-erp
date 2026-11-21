import { EventEmitter } from 'node:events';
import { createRequire } from 'node:module';
import { describe, expect, it, vi } from 'vitest';
import type { OmniUpdaterBridge, UpdaterActionResult, UpdaterStatusPayload } from '../types/electron';

const require = createRequire(import.meta.url);

interface UpdaterController {
  init: () => { enabled: boolean };
  cleanup: () => void;
  checkForUpdates: () => Promise<UpdaterActionResult>;
  downloadUpdate: () => Promise<UpdaterActionResult>;
  installUpdate: () => UpdaterActionResult;
  isEnabled: () => boolean;
  getState: () => {
    enabled: boolean;
    initialized: boolean;
    status: string;
    version?: string;
    hasUpdateAvailable: boolean;
    hasDownloadedUpdate: boolean;
  };
}

interface UpdaterModule {
  IPC_CHANNELS: {
    CHECK: string;
    DOWNLOAD: string;
    INSTALL: string;
    STATUS: string;
  };
  UPDATER_DISABLED_MESSAGE: string;
  ERROR_MESSAGES: {
    NETWORK_ERROR: string;
    SIGNATURE_ERROR: string;
    UNAVAILABLE: string;
    UPDATER_ERROR: string;
  };
  sanitizeUpdaterError: (err: unknown) => { code: string; message: string };
  isUpdaterEnabled: (opts?: {
    app?: { isPackaged?: boolean } | null;
    env?: Record<string, string | undefined> | null;
  }) => boolean;
  createUpdaterController: (deps?: Record<string, unknown>) => UpdaterController;
}

interface PreloadModule {
  UPDATER_CHANNELS: {
    CHECK: string;
    DOWNLOAD: string;
    INSTALL: string;
    STATUS: string;
  };
  exposePreloadBridges: (
    contextBridge: { exposeInMainWorld: (key: string, api: unknown) => void },
    ipcRenderer: {
      invoke: (channel: string) => Promise<unknown>;
      on: (channel: string, listener: (...args: unknown[]) => void) => void;
      off?: (channel: string, listener: (...args: unknown[]) => void) => void;
      removeListener?: (channel: string, listener: (...args: unknown[]) => void) => void;
    },
    platform?: string,
  ) => void;
}

const updaterMod = require('../../electron/updater.cjs') as UpdaterModule;
const preloadMod = require('../../electron/preload.cjs') as PreloadModule;

class FakeAutoUpdater extends EventEmitter {
  autoDownload = true;
  logger: unknown = console;
  checkForUpdates = vi.fn<() => Promise<unknown>>(async () => null);
  downloadUpdate = vi.fn<() => Promise<string[]>>(async () => []);
  quitAndInstall = vi.fn<() => void>();
}

function createFakeIpcMain() {
  const handlers = new Map<string, (event?: unknown) => Promise<unknown>>();
  return {
    handlers,
    handle: vi.fn((channel: string, handler: (event?: unknown) => Promise<unknown>) => {
      handlers.set(channel, handler);
    }),
    removeHandler: vi.fn((channel: string) => {
      handlers.delete(channel);
    }),
    async invoke(channel: string, event?: unknown): Promise<UpdaterActionResult> {
      const handler = handlers.get(channel);
      if (!handler) {
        throw new Error(`No handler registered for ${channel}`);
      }
      return (await handler(event)) as UpdaterActionResult;
    },
  };
}

function createFakeWindow(options?: { destroyed?: boolean; wcDestroyed?: boolean }) {
  const send = vi.fn();
  const webContents = {
    send,
    isDestroyed: vi.fn(() => Boolean(options?.wcDestroyed)),
  };
  const win = {
    webContents,
    isDestroyed: vi.fn(() => Boolean(options?.destroyed)),
  };
  return { win, send, webContents };
}

describe('electron/updater.cjs', () => {
  it('solo activa auto-update cuando app.isPackaged === true y OMNI_DISABLE_AUTO_UPDATE !== "1"', () => {
    expect(updaterMod.isUpdaterEnabled({ app: { isPackaged: false }, env: {} })).toBe(false);
    expect(
      updaterMod.isUpdaterEnabled({
        app: { isPackaged: true },
        env: { OMNI_DISABLE_AUTO_UPDATE: '1' },
      }),
    ).toBe(false);
    expect(
      updaterMod.isUpdaterEnabled({
        app: { isPackaged: true },
        env: { OMNI_DISABLE_AUTO_UPDATE: '0' },
      }),
    ).toBe(true);
  });

  it('en desarrollo o con OMNI_DISABLE_AUTO_UPDATE=1 no toca autoUpdater ni hace red', async () => {
    for (const scenario of [
      { app: { isPackaged: false }, env: {} },
      { app: { isPackaged: true }, env: { OMNI_DISABLE_AUTO_UPDATE: '1' } },
    ]) {
      const autoUpdater = new FakeAutoUpdater();
      const ipcMain = createFakeIpcMain();
      const { win, send } = createFakeWindow();
      const controller = updaterMod.createUpdaterController({
        autoUpdater,
        app: scenario.app,
        ipcMain,
        getWindow: () => win,
        env: scenario.env,
      });

      const initResult = controller.init();
      expect(initResult.enabled).toBe(false);
      expect(controller.isEnabled()).toBe(false);
      expect(autoUpdater.listenerCount('checking-for-update')).toBe(0);

      const checkRes = await ipcMain.invoke(updaterMod.IPC_CHANNELS.CHECK);
      const downloadRes = await ipcMain.invoke(updaterMod.IPC_CHANNELS.DOWNLOAD);
      const installRes = await ipcMain.invoke(updaterMod.IPC_CHANNELS.INSTALL);

      expect(checkRes).toEqual({
        ok: false,
        status: 'disabled',
        error: updaterMod.UPDATER_DISABLED_MESSAGE,
      });
      expect(downloadRes.status).toBe('disabled');
      expect(installRes.status).toBe('disabled');
      expect(autoUpdater.checkForUpdates).not.toHaveBeenCalled();
      expect(autoUpdater.downloadUpdate).not.toHaveBeenCalled();
      expect(autoUpdater.quitAndInstall).not.toHaveBeenCalled();
      expect(send).not.toHaveBeenCalled();

      controller.cleanup();
      expect(ipcMain.handlers.size).toBe(0);
    }
  });

  it('reenvía eventos de estado solo si mainWindow existe y no está destruida', () => {
    const autoUpdater = new FakeAutoUpdater();
    const ipcMain = createFakeIpcMain();
    let activeWin: ReturnType<typeof createFakeWindow>['win'] | null = null;
    const controller = updaterMod.createUpdaterController({
      autoUpdater,
      app: { isPackaged: true },
      ipcMain,
      getWindow: () => activeWin,
      env: {},
    });

    expect(controller.init().enabled).toBe(true);
    expect(autoUpdater.autoDownload).toBe(false);

    // Sin ventana: no falla ni lanza
    autoUpdater.emit('checking-for-update');

    // Con ventana viva: reenvía eventos saneados
    const live = createFakeWindow();
    activeWin = live.win;
    autoUpdater.emit('update-available', {
      version: '1.2.3',
      releaseDate: '2026-11-21T10:00:00.000Z',
    });
    autoUpdater.emit('download-progress', {
      percent: 42.3456,
      bytesPerSecond: 102400,
      transferred: 4200,
      total: 10000,
    });
    autoUpdater.emit('update-not-available', {
      version: '1.2.2',
    });

    expect(live.send).toHaveBeenNthCalledWith(1, updaterMod.IPC_CHANNELS.STATUS, {
      status: 'available',
      version: '1.2.3',
      releaseDate: '2026-11-21T10:00:00.000Z',
    });
    expect(live.send).toHaveBeenNthCalledWith(2, updaterMod.IPC_CHANNELS.STATUS, {
      status: 'downloading',
      progress: {
        percent: 42.35,
        bytesPerSecond: 102400,
        transferred: 4200,
        total: 10000,
      },
    });
    expect(live.send).toHaveBeenNthCalledWith(3, updaterMod.IPC_CHANNELS.STATUS, {
      status: 'not-available',
      version: '1.2.2',
    });

    // Ventana destruida: no envía más
    const destroyed = createFakeWindow({ destroyed: true });
    activeWin = destroyed.win;
    autoUpdater.emit('update-downloaded', { version: '1.2.3' });
    expect(destroyed.send).not.toHaveBeenCalled();

    // webContents destruido: tampoco envía
    const wcDestroyed = createFakeWindow({ wcDestroyed: true });
    activeWin = wcDestroyed.win;
    autoUpdater.emit('checking-for-update');
    expect(wcDestroyed.send).not.toHaveBeenCalled();

    controller.cleanup();
  });

  it('bloquea updater:install y updater:download si no hay actualización lista y permite instalar tras update-downloaded', async () => {
    const autoUpdater = new FakeAutoUpdater();
    const ipcMain = createFakeIpcMain();
    const { win, send, webContents } = createFakeWindow();
    const validEvent = {
      sender: webContents,
      senderFrame: { url: 'app://omni/' },
    };

    const controller = updaterMod.createUpdaterController({
      autoUpdater,
      app: { isPackaged: true },
      ipcMain,
      getWindow: () => win,
      env: {},
    });
    controller.init();

    // Sin actualización disponible/descargada: bloquea download e install
    const prematureDownload = await ipcMain.invoke(updaterMod.IPC_CHANNELS.DOWNLOAD, validEvent);
    expect(prematureDownload.ok).toBe(false);
    expect(autoUpdater.downloadUpdate).not.toHaveBeenCalled();

    const prematureInstall = await ipcMain.invoke(updaterMod.IPC_CHANNELS.INSTALL, validEvent);
    expect(prematureInstall.ok).toBe(false);
    expect(autoUpdater.quitAndInstall).not.toHaveBeenCalled();

    // Rechaza origen IPC no autorizado
    const rogueInstall = await ipcMain.invoke(updaterMod.IPC_CHANNELS.INSTALL, {
      sender: {},
      senderFrame: { url: 'https://evil.example/' },
    });
    expect(rogueInstall.ok).toBe(false);
    expect(autoUpdater.quitAndInstall).not.toHaveBeenCalled();

    // Flujo completo check -> available -> download -> downloaded -> install
    autoUpdater.checkForUpdates.mockImplementationOnce(async () => {
      autoUpdater.emit('checking-for-update');
      autoUpdater.emit('update-available', { version: '2.0.0' });
      return { updateInfo: { version: '2.0.0' } };
    });
    const checkRes = await ipcMain.invoke(updaterMod.IPC_CHANNELS.CHECK, validEvent);
    expect(checkRes).toEqual({ ok: true, status: 'available', version: '2.0.0' });

    // Antes de descargar sigue bloqueado install
    const stillBlocked = await ipcMain.invoke(updaterMod.IPC_CHANNELS.INSTALL, validEvent);
    expect(stillBlocked.ok).toBe(false);
    expect(autoUpdater.quitAndInstall).not.toHaveBeenCalled();

    autoUpdater.downloadUpdate.mockImplementationOnce(async () => {
      autoUpdater.emit('update-downloaded', { version: '2.0.0' });
      return ['/tmp/omni.AppImage'];
    });
    const downloadRes = await ipcMain.invoke(updaterMod.IPC_CHANNELS.DOWNLOAD, validEvent);
    expect(downloadRes).toEqual({ ok: true, status: 'downloaded', version: '2.0.0' });

    const installRes = await ipcMain.invoke(updaterMod.IPC_CHANNELS.INSTALL, validEvent);
    expect(installRes).toEqual({ ok: true, status: 'installing', version: '2.0.0' });
    expect(autoUpdater.quitAndInstall).toHaveBeenCalledTimes(1);
    expect(send).toHaveBeenCalledWith(updaterMod.IPC_CHANNELS.STATUS, {
      status: 'installing',
      version: '2.0.0',
    });

    controller.cleanup();
  });

  it('maneja errores de red, firma y quitAndInstall de forma fail-safe sin filtrar stack traces ni URLs', async () => {
    const autoUpdater = new FakeAutoUpdater();
    const ipcMain = createFakeIpcMain();
    const { win, send } = createFakeWindow();
    const controller = updaterMod.createUpdaterController({
      autoUpdater,
      app: { isPackaged: true },
      ipcMain,
      getWindow: () => win,
      env: {},
    });
    controller.init();

    // 1) Error de red con URL privada y stack trace
    const networkErr = new Error(
      'net::ERR_NAME_NOT_RESOLVED at https://updates.internal.example/release/latest.yml',
    );
    networkErr.stack = 'Error: internal trace\n    at C:\\Users\\admin\\app.js:10:5';
    autoUpdater.checkForUpdates.mockRejectedValueOnce(networkErr);

    const netResult = await controller.checkForUpdates();
    expect(netResult).toEqual({
      ok: false,
      status: 'error',
      error: updaterMod.ERROR_MESSAGES.NETWORK_ERROR,
      errorCode: 'NETWORK_ERROR',
    });
    expect(netResult.error).not.toContain('updates.internal.example');
    expect(netResult.error).not.toContain('internal trace');
    expect(netResult.error).not.toContain('C:\\Users');

    // 2) Error de firma emitido por evento mientras checkForUpdates resuelve null
    autoUpdater.checkForUpdates.mockImplementationOnce(async () => {
      autoUpdater.emit(
        'error',
        new Error('New version 2.1.0 is not signed by the application owner: C:\\temp\\setup.exe'),
      );
      return null;
    });
    const sigResult = await controller.checkForUpdates();
    expect(sigResult).toEqual({
      ok: false,
      status: 'error',
      error: updaterMod.ERROR_MESSAGES.SIGNATURE_ERROR,
      errorCode: 'SIGNATURE_ERROR',
    });
    expect(send).toHaveBeenLastCalledWith(updaterMod.IPC_CHANNELS.STATUS, {
      status: 'error',
      error: updaterMod.ERROR_MESSAGES.SIGNATURE_ERROR,
      errorCode: 'SIGNATURE_ERROR',
    });

    // 3) Error 404 / app-update.yml faltante
    expect(updaterMod.sanitizeUpdaterError(new Error('HttpError: 404 Not Found'))).toEqual({
      code: 'UNAVAILABLE',
      message: updaterMod.ERROR_MESSAGES.UNAVAILABLE,
    });

    // 4) Error síncrono en quitAndInstall tras descarga no tumba el proceso
    autoUpdater.emit('update-downloaded', { version: '2.1.0' });
    autoUpdater.quitAndInstall.mockImplementationOnce(() => {
      throw new Error('EACCES C:\\Program Files\\OmniERP\\uninstall.exe');
    });
    const installErr = controller.installUpdate();
    expect(installErr).toEqual({
      ok: false,
      status: 'error',
      error: updaterMod.ERROR_MESSAGES.UPDATER_ERROR,
      errorCode: 'UPDATER_ERROR',
    });
    expect(installErr.error).not.toContain('Program Files');

    controller.cleanup();
  });

  it('limpia todos los listeners de autoUpdater y handlers IPC en cleanup()', () => {
    const autoUpdater = new FakeAutoUpdater();
    const ipcMain = createFakeIpcMain();
    const controller = updaterMod.createUpdaterController({
      autoUpdater,
      app: { isPackaged: true },
      ipcMain,
      getWindow: () => null,
      env: {},
    });

    controller.init();
    ipcMain.removeHandler.mockClear();
    expect(autoUpdater.listenerCount('checking-for-update')).toBe(1);
    expect(autoUpdater.listenerCount('update-available')).toBe(1);
    expect(autoUpdater.listenerCount('update-not-available')).toBe(1);
    expect(autoUpdater.listenerCount('download-progress')).toBe(1);
    expect(autoUpdater.listenerCount('update-downloaded')).toBe(1);
    expect(autoUpdater.listenerCount('error')).toBe(1);
    expect(ipcMain.handlers.size).toBe(3);

    autoUpdater.emit('update-downloaded', { version: '1.5.0' });
    expect(controller.getState().hasDownloadedUpdate).toBe(true);

    controller.cleanup();
    expect(autoUpdater.listenerCount('checking-for-update')).toBe(0);
    expect(autoUpdater.listenerCount('update-available')).toBe(0);
    expect(autoUpdater.listenerCount('update-not-available')).toBe(0);
    expect(autoUpdater.listenerCount('download-progress')).toBe(0);
    expect(autoUpdater.listenerCount('update-downloaded')).toBe(0);
    expect(autoUpdater.listenerCount('error')).toBe(0);
    expect(ipcMain.handlers.size).toBe(0);
    expect(ipcMain.removeHandler).toHaveBeenCalledTimes(3);
    expect(ipcMain.removeHandler).toHaveBeenCalledWith(updaterMod.IPC_CHANNELS.CHECK);
    expect(ipcMain.removeHandler).toHaveBeenCalledWith(updaterMod.IPC_CHANNELS.DOWNLOAD);
    expect(ipcMain.removeHandler).toHaveBeenCalledWith(updaterMod.IPC_CHANNELS.INSTALL);
    expect(controller.getState().hasDownloadedUpdate).toBe(false);
    expect(controller.getState().initialized).toBe(false);

    // Idempotente en segunda llamada
    expect(() => controller.cleanup()).not.toThrow();
  });
});

describe('electron/preload.cjs', () => {
  it('expone omniDesktop y omniUpdater vía contextBridge sin filtrar el evento IPC interno', async () => {
    const exposed = new Map<string, unknown>();
    const emitter = new EventEmitter();
    const invoke = vi.fn(async (channel: string) => ({ ok: true, status: channel }));

    const fakeContextBridge = {
      exposeInMainWorld: vi.fn((key: string, api: unknown) => {
        exposed.set(key, api);
      }),
    };
    const fakeIpcRenderer = {
      invoke,
      on: vi.fn((channel: string, listener: (...args: unknown[]) => void) => {
        emitter.on(channel, listener);
      }),
      off: vi.fn((channel: string, listener: (...args: unknown[]) => void) => {
        emitter.off(channel, listener);
      }),
    };

    preloadMod.exposePreloadBridges(fakeContextBridge, fakeIpcRenderer, 'linux');

    expect(exposed.get('omniDesktop')).toEqual({
      isElectron: true,
      platform: 'linux',
    });

    const updaterBridge = exposed.get('omniUpdater') as OmniUpdaterBridge;
    expect(updaterBridge).toBeDefined();

    await updaterBridge.checkForUpdates();
    await updaterBridge.downloadUpdate();
    await updaterBridge.installUpdate();
    expect(invoke).toHaveBeenNthCalledWith(1, preloadMod.UPDATER_CHANNELS.CHECK);
    expect(invoke).toHaveBeenNthCalledWith(2, preloadMod.UPDATER_CHANNELS.DOWNLOAD);
    expect(invoke).toHaveBeenNthCalledWith(3, preloadMod.UPDATER_CHANNELS.INSTALL);

    const received: UpdaterStatusPayload[] = [];
    const argCounts: number[] = [];
    const unsubscribe = updaterBridge.onStatus((...args) => {
      argCounts.push(args.length);
      received.push(args[0]);
    });

    emitter.emit(preloadMod.UPDATER_CHANNELS.STATUS, { senderId: 99 }, {
      status: 'available',
      version: '3.0.0',
    });
    expect(argCounts).toEqual([1]);
    expect(received).toEqual([{ status: 'available', version: '3.0.0' }]);

    unsubscribe();
    expect(emitter.listenerCount(preloadMod.UPDATER_CHANNELS.STATUS)).toBe(0);

    // Callback inválido no registra listener ni rompe
    const noopUnsub = updaterBridge.onStatus('not-a-fn' as unknown as (p: UpdaterStatusPayload) => void);
    expect(() => noopUnsub()).not.toThrow();
    expect(emitter.listenerCount(preloadMod.UPDATER_CHANNELS.STATUS)).toBe(0);
  });
});
