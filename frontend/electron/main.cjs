// Proceso principal de Electron — shell de escritorio (Windows) de Omni ERP.
// Carga el dev server de Vite en desarrollo o el bundle estático en producción.
const { app, BrowserWindow, shell } = require('electron');
const path = require('path');

const DEV_URL = process.env.ELECTRON_START_URL || 'http://localhost:5173';
const isDev = !app.isPackaged;

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
    // dist/ se empaqueta junto a electron/ dentro de los recursos de la app.
    mainWindow.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
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
  createWindow();
  app.on('activate', () => {
    if (BrowserWindow.getAllWindows().length === 0) createWindow();
  });
});

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') app.quit();
});
