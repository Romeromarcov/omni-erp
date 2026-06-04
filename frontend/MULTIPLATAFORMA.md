# Omni ERP — Frontend multiplataforma

Una sola base de código **React + Vite + MUI** corre en cuatro destinos:

| Destino | Tecnología | Estado |
|---|---|---|
| Web / PWA (instalable) | Vite + vite-plugin-pwa | ✅ Listo |
| Windows (escritorio) | Electron + electron-builder | ✅ Listo (compila `.exe`) |
| Android | Capacitor | ✅ Listo para compilar (requiere Android SDK + JDK) |
| iOS | Capacitor | ✅ Listo para compilar (requiere macOS + Xcode) |

La adaptación por plataforma vive en [`src/platform/`](src/platform/): detección
de entorno, **router adaptativo** (rutas limpias en web, *hash routing* en shells
nativos) e inicialización del shell nativo (status bar, safe-areas, botón atrás
de Android).

## Integración con el backend

La URL del backend se inyecta en build con **`VITE_API_URL`** (ver
`src/services/api.ts`, que hace *fail-fast* en producción si falta):

```
VITE_API_URL=https://api.tu-dominio.com/api
```

- **Web**: en dev usa el proxy `/api` de Vite (`vite.config.ts`); en prod, `VITE_API_URL`.
- **Nativo (Electron/Capacitor)**: NO hay proxy ni mismo origen → `VITE_API_URL`
  debe ser una URL absoluta al backend. Además el backend debe permitir CORS para
  el origen nativo y, como la sesión usa cookie httpOnly de refresh, habilitar
  `credentials`/`SameSite=None; Secure` para los orígenes `capacitor://`,
  `https://localhost` (Android) y `file://`/`app://` (Electron).

## Comandos

```bash
# Web / PWA
npm run dev                 # desarrollo
VITE_API_URL=… npm run build

# Build nativo (base relativa + hash router)
VITE_API_URL=… npm run build:native

# Windows (Electron)
npm run electron:start                      # corre el dev server embebido
VITE_API_URL=… npm run electron:build       # genera instalador NSIS + portable en release/

# Android (Capacitor) — requiere Android Studio / SDK + JDK 17
VITE_API_URL=… npm run build:native
npm run cap:add:android      # solo la primera vez
npm run cap:sync
npm run cap:open:android     # abre Android Studio para compilar el APK/AAB

# iOS (Capacitor) — requiere macOS + Xcode + CocoaPods
VITE_API_URL=… npm run build:native
npm run cap:add:ios          # solo la primera vez (en macOS)
npm run cap:sync
npm run cap:open:ios
```

> Los proyectos nativos generados (`android/`, `ios/`) y la salida de Electron
> (`release/`) están en `.gitignore`: se regeneran con `cap add` / `electron:build`
> en el toolchain de cada plataforma.

## Escáner (cámara / QR / NFC)

[`src/services/scannerHardware.ts`](src/services/scannerHardware.ts) usa hardware
real con detección de capacidades:

- **Cámara + códigos (barras/QR)**: `getUserMedia` + `BarcodeDetector` (web,
  Android/Chromium WebView, Electron). Si no hay soporte → lector manual.
- **NFC**: Web NFC (`NDEFReader`) en Android Chrome. Si no hay soporte → lector manual.
- En iOS (sin `BarcodeDetector`) se puede enchufar el plugin nativo de Capacitor
  (ML Kit) detrás del mismo contrato sin tocar la UI.

La resolución del código a una entidad de Omni (`resolveScan` en
`scannerService.ts`) es el punto donde se conecta la búsqueda real de inventario/
documentos/clientes del backend.
