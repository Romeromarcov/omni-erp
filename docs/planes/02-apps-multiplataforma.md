# Plan B — Apps por plataforma (firmadas + CI de empaquetado)

| Campo | Valor |
|-------|-------|
| **Objetivo** | Apps distribuibles y firmadas, con empaquetado automatizado en CI. Orden: Windows → Android → desktop macOS/Linux; **iOS diferido**. |
| **Estado actual** | Andamiaje completo (Electron 42, Capacitor 8, PWA). **Sin firma, sin job de empaquetado en CI, sin artefactos publicados.** |
| **Esfuerzo** | ~3–4 semanas (sin iOS). |
| **Deuda** | [CTF-010](../ctf/CTF-010.md). |

## Punto de partida (verificado en código)

- Desktop: `frontend/electron-builder.json` (targets `nsis` + `portable` Windows; macOS/Linux configurables), `frontend/electron/main.cjs`, script `npm run electron:build`.
- Móvil: `frontend/capacitor.config.ts`, deps `@capacitor/{core,cli,android,ios}@8`, scripts `cap:*`.
- PWA: `frontend/vite.config.ts` (VitePWA), artefactos en `dist/`.
- Docs: `frontend/MULTIPLATAFORMA.md`.
- **CI (`.github/workflows/ci.yml`) NO compila ni publica binarios.** Carpetas `release/`, `android/`, `ios/` en `.gitignore`.

## Fase transversal previa — Corregir drift de rol · ~0.5 día
Antes de cablear guards de plataforma/proveedor: alinear `es_superusuario_innova`
(frontend, `frontend/src/services/users.ts`) con `es_superusuario_omni` (backend).
Ver [CTF-009](../ctf/CTF-009.md).

## Fase B1 — Windows productivo · ~1 semana
- Auto-update con `electron-updater` apuntando a releases de GitHub.
- **Firma Authenticode** (cert EV) → elimina SmartScreen. (Compra del certificado = lead time externo.)
- **Job de CI de empaquetado** (nuevo): build `.exe` en GitHub Actions (runner Windows) y publicar como artefacto/release.
- **DoD:** un release de GitHub publica un `.exe` firmado descargable; auto-update funciona.

## Fase B2 — Android · ~1–2 semanas
- `npm run cap:add:android`, generar **keystore**, configurar firma, target `.aab` para Play Store.
- Permisos nativos (cámara/escáner QR/NFC ya contemplados en `MULTIPLATAFORMA.md`).
- CI con runner con Android SDK + JDK 17; cuenta de Google Play Console.
- **DoD:** `.aab` firmado generado en CI; instalable en dispositivo real.

## Fase B3 — Desktop macOS / Linux · ~3–4 días (oportunista)
- Activar targets en `electron-builder.json` (`.dmg`, AppImage). macOS requiere build en Mac + notarización Apple.
- **DoD:** AppImage Linux en CI; `.dmg` documentado (requiere Mac).

## Fase B4 — iOS · DIFERIDO
- Requiere macOS + Xcode + cuenta Apple Developer + provisioning profiles.
- Abrir solo cuando exista demanda real (decisión del usuario).

## Definition of Done (global)

- [ ] Windows `.exe` firmado y auto-actualizable, publicado vía CI.
- [ ] Android `.aab` firmado generado en CI.
- [x] Drift de rol corregido ([CTF-009](../ctf/CTF-009.md) — CERRADO 2026-06-07).
- [ ] Documentación de release por plataforma actualizada en `frontend/MULTIPLATAFORMA.md`.
- [ ] [CTF-010](../ctf/CTF-010.md) cerrado con fecha real.
