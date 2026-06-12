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
  debe ser una URL absoluta al backend.

### Orígenes de los shells nativos (CORS + cookie de refresh)

| Shell | Origen | Cómo se obtiene |
|---|---|---|
| Electron (Windows) | `app://omni` | `electron/main.cjs` sirve `dist/` bajo un scheme propio registrado como `standard+secure`. **Nunca** se usa `file://` (su `Origin: null` lo comparten los iframes sandboxeados de cualquier web y permitirlo en CORS sería inseguro). |
| Android (Capacitor) | `https://localhost` | `androidScheme: 'https'` en `capacitor.config.ts`. |
| iOS (Capacitor, futuro) | `capacitor://localhost` | Default de Capacitor en iOS. |

El backend ya permite estos tres orígenes en producción (`settings_prod.py`,
flag `CORS_NATIVE_SHELLS`, default on). Además, como la sesión usa cookie
httpOnly de refresh **cross-site**, el backend necesita
`REFRESH_TOKEN_COOKIE_SAMESITE=None` (ya configurado en Railway, donde el
frontend web también es cross-site respecto del backend).

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
npm run cap:patch:android    # agrega permisos CAMERA/NFC al manifest generado
npm run cap:open:android     # abre Android Studio para compilar el APK/AAB

# iOS (Capacitor) — requiere macOS + Xcode + CocoaPods
VITE_API_URL=… npm run build:native
npm run cap:add:ios          # solo la primera vez (en macOS)
npm run cap:sync
npm run cap:open:ios
```

> Los proyectos nativos generados (`android/`, `ios/`) y la salida de Electron
> (`release/`) están en `.gitignore`: se regeneran con `cap add` / `electron:build`
> en el toolchain de cada plataforma. Toda personalización del proyecto Android
> (p. ej. permisos del manifest) vive en `scripts/patch-android-manifest.mjs`,
> nunca editada a mano dentro de `android/`.

## Empaquetado en CI (binarios distribuibles)

El workflow [`.github/workflows/package.yml`](../.github/workflows/package.yml)
compila los binarios en GitHub Actions:

- **Windows**: `OmniERP-<version>-setup.exe` (instalador NSIS) +
  `OmniERP-<version>-portable.exe`, en runner Windows.
- **Android**: `.apk` debug siempre; `.apk` release firmado + `.aab` (Play Store)
  cuando existen los secrets `ANDROID_KEYSTORE_BASE64`, `ANDROID_KEYSTORE_PASSWORD`,
  `ANDROID_KEY_ALIAS` y `ANDROID_KEY_PASSWORD`.

Disparo: manual (*Actions → Package — apps nativas → Run workflow*, con la URL
del backend como input) o tageando `app-v*` (además crea un GitHub Release en
draft con los binarios).

**Firma pendiente** ([CTF-010](../docs/ctf/CTF-010.md)): los `.exe` van sin
Authenticode (SmartScreen avisa) hasta comprar el certificado EV; el keystore
Android se genera una vez (`keytool -genkeypair`) y se carga en secrets.

### Generar el keystore Android (una sola vez)

```bash
keytool -genkeypair -v -keystore omni-release.keystore -alias omni \
  -keyalg RSA -keysize 2048 -validity 10000
# Subir a GitHub secrets:
#   ANDROID_KEYSTORE_BASE64  = base64 del archivo (base64 -w0 omni-release.keystore)
#   ANDROID_KEYSTORE_PASSWORD / ANDROID_KEY_ALIAS / ANDROID_KEY_PASSWORD
# Guardar el .keystore en un lugar seguro: perderlo = no poder actualizar la app.
```

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
