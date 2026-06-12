// Proceso principal de Electron — shell de escritorio (Windows) de Omni ERP.
// Carga el dev server de Vite en desarrollo o el bundle estático en producción.
//
// En producción la app NO se sirve desde file:// sino desde el scheme propio
// app://omni. Motivo (seguridad + CORS): con file:// el navegador manda
// `Origin: null` en cada fetch cross-origin al backend, y permitir el origen
// "null" en CORS del servidor abriría la puerta a cualquier iframe sandboxeado.
// Con un scheme standard+secure el origen es estable (`app://omni`) y el
// backend lo permite explícitamente (ver settings_prod.py, CORS de shells).
const { app, BrowserWindow, net, protocol, shell } = require('electron');
const fs = require('fs');
const path = require('path');
const { pathToFileURL } = require('url');

const DEV_URL = process.env.ELECTRON_START_URL || 'http://localhost:5173';
const APP_SCHEME = 'app';
const APP_HOST = 'omni';
const isDev = !app.isPackaged;

// Debe ejecutarse ANTES de app.ready.
protocol.registerSchemesAsPrivileged([
  {
    scheme: APP_SCHEME,
    privileges: {
      standard: true,
      secure: true,
      supportsFetchAPI: true,
      corsEnabled: true,
      // El build PWA registra un service worker; sin esto la registración
      // fallaría en un scheme custom (en web/Android sí aplica el SW).
      allowServiceWorkers: true,
    },
  },
]);

/** Sirve dist/ bajo app://omni/ con fallback a index.html (SPA). */
function registerAppProtocol() {
  const distDir = path.join(__dirname, '..', 'dist');
  protocol.handle(APP_SCHEME, (request) => {
    const { pathname } = new URL(request.url);
    const relative = decodeURIComponent(pathname).replace(/^\/+/, '');
    // El service worker de la PWA no aporta en escritorio (assets locales) y
    // el precache de Workbox falla sobre schemes custom ("Failed to fetch").
    // Solo el shell de Electron lo neutraliza; web y Android lo conservan.
    if (relative === 'registerSW.js') {
      return new Response('/* service worker deshabilitado en escritorio */', {
        headers: { 'content-type': 'text/javascript' },
      });
    }
    const resolved = path.normalize(path.join(distDir, relative));
    // Anti path-traversal: nunca servir fuera de dist/.
    const safe =
      resolved.startsWith(distDir + path.sep) || resolved === distDir;
    // eslint-disable-next-line security/detect-non-literal-fs-filename -- FP: `resolved` está canonicalizada (path.normalize) y el chequeo `safe` la confina a dist/ (anti path-traversal, ver líneas anteriores)
    if (safe && relative && fs.existsSync(resolved) && fs.statSync(resolved).isFile()) {
      return net.fetch(pathToFileURL(resolved).toString());
    }
    // Fallback SPA solo para navegaciones (rutas sin extensión). Un asset
    // inexistente (p. ej. chunk perdido) debe dar 404 diagnosticable, no un
    // index.html con MIME equivocado que además podría cachear el SW.
    if (!path.extname(relative)) {
      return net.fetch(pathToFileURL(path.join(distDir, 'index.html')).toString());
    }
    return new Response('Not found', { status: 404 });
  });
}

/** @type {BrowserWindow | null} */
let mainWindow = null;

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1024,
    minHeight: 640,
    backgroundColor: '#f4f6f8',
    autoHideMenuBar: true,
    title: 'Omni ERP',
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  if (isDev) {
    mainWindow.loadURL(DEV_URL);
    mainWindow.webContents.openDevTools({ mode: 'detach' });
  } else {
    mainWindow.loadURL(`${APP_SCHEME}://${APP_HOST}/`);
  }

  // Abrir enlaces externos en el navegador del sistema, no en la app.
  mainWindow.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('http://') || url.startsWith('https://')) {
      shell.openExternal(url);
      return { action: 'deny' };
    }
    return { action: 'allow' };
  });

  mainWindow.on('closed', () => {
    mainWindow = null;
  });
}

app.whenReady().then(() => {
  if (!isDev) registerAppProtocol();
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
