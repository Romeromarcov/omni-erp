# Plan B — Apps por plataforma (firmadas + CI de empaquetado)

| Campo | Valor |
|-------|-------|
| **Objetivo** | Apps distribuibles y firmadas, con empaquetado automatizado en CI. Orden: Windows → Android → desktop macOS/Linux; **iOS diferido**. |
| **Estado actual** | Andamiaje completo (Electron 42 + `electron-updater` fail-safe, Capacitor 8, PWA). **CI de empaquetado operativo** (`.github/workflows/package.yml`: `.exe` + `*.blockmap` + `latest.yml` Windows, `.AppImage` + `latest-linux.yml` Linux, `.apk`/`.aab` Android; release draft en tags `app-v*`). CORS de shells nativos habilitado en backend (`app://omni`, `https://localhost`). **Firma Authenticode Windows (`CSC_LINK`/`CSC_KEY_PASSWORD`) y keystore Android opt-in vía secrets (pendiente certificados del owner en CTF-010).** |
| **Esfuerzo** | ~3–4 semanas (sin iOS). |
| **Deuda** | [CTF-010](../ctf/CTF-010.md). |

## Punto de partida (verificado en código)

- Desktop: `frontend/electron-builder.json` (`publish` GitHub `Romeromarcov/omni-erp`, targets `nsis` + `portable` Windows, `dmg` macOS, `AppImage` Linux), `frontend/electron/main.cjs`, `frontend/electron/updater.cjs`, `frontend/electron/preload.cjs`, scripts `npm run electron:build` y `npm run electron:build:linux`.
- Móvil: `frontend/capacitor.config.ts`, deps `@capacitor/{core,cli,android,ios}@8`, scripts `cap:*`.
- PWA: `frontend/vite.config.ts` (VitePWA), artefactos en `dist/`.
- Docs: `frontend/MULTIPLATAFORMA.md`.
- **CI (`.github/workflows/ci.yml`) NO compila ni publica binarios.** Carpetas `release/`, `android/`, `ios/` en `.gitignore`.

## Fase transversal previa — Corregir drift de rol · ~0.5 día
Antes de cablear guards de plataforma/proveedor: alinear `es_superusuario_innova`
(frontend, `frontend/src/services/users.ts`) con `es_superusuario_omni` (backend).
Ver [CTF-009](../ctf/CTF-009.md).

## Fase B1 — Windows productivo · ~1 semana
- Auto-update con `electron-updater` apuntando a releases de GitHub (`frontend/electron/updater.cjs`, `preload.cjs`, `electron-builder.json` — implementado con manejo fail-safe y `autoDownload = false`).
- **Firma Authenticode** (cert EV, opt-in en CI con `CSC_LINK`/`CSC_KEY_PASSWORD`) → elimina SmartScreen. (Compra del certificado = lead time externo, [CTF-010](../ctf/CTF-010.md).)
- **Job de CI de empaquetado**: build `.exe` + `*.blockmap` + `latest.yml` en GitHub Actions (runner Windows) y publicación como artefacto/release draft.
- **DoD:** un release de GitHub publica un `.exe` firmado descargable; auto-update funciona.

## Fase B2 — Android · ~1–2 semanas
- `npm run cap:add:android`, generar **keystore**, configurar firma, target `.aab` para Play Store.
- Permisos nativos (cámara/escáner QR/NFC ya contemplados en `MULTIPLATAFORMA.md`).
- CI con runner con Android SDK + JDK 21 (Capacitor 8); cuenta de Google Play Console.
- **DoD:** `.aab` firmado generado en CI; instalable en dispositivo real.

## Fase B3 — Desktop macOS / Linux · ~3–4 días (oportunista)
- Targets activos en `electron-builder.json` (`AppImage` Linux, `dmg` macOS). Job `linux` en `.github/workflows/package.yml` compila `.AppImage` + `latest-linux.yml` en `ubuntu-latest`. macOS requiere build en Mac + notarización Apple.
- **DoD:** AppImage Linux en CI (implementado); `.dmg` documentado (requiere Mac).

## Fase B4 — iOS · DIFERIDO
- Requiere macOS + Xcode + cuenta Apple Developer + provisioning profiles.
- Abrir solo cuando exista demanda real (decisión del usuario).

## Definition of Done (global)

- [ ] Windows `.exe` firmado (pendiente cert EV del owner) y auto-actualizable (`electron-updater` implementado), publicado vía CI.
- [ ] Android `.aab` firmado generado en CI (pendiente keystore del owner en secrets).
- [x] Linux `.AppImage` + `latest-linux.yml` generado en CI y release draft `app-v*`.
- [x] Drift de rol corregido ([CTF-009](../ctf/CTF-009.md) — CERRADO 2026-06-07).
- [x] Documentación de release y auto-update por plataforma actualizada en `frontend/MULTIPLATAFORMA.md`.
- [ ] [CTF-010](../ctf/CTF-010.md) cerrado con fecha real (abierto hasta cargar cert EV Authenticode y keystore Android).
