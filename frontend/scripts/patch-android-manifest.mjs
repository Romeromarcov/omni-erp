// Parchea el AndroidManifest.xml generado por `cap add android` (carpeta
// android/ está en .gitignore y se regenera en cada toolchain/CI, por lo que
// las personalizaciones del manifest deben aplicarse por script, no a mano).
//
// Agrega los permisos que el shell Android necesita además de INTERNET:
//   - CAMERA: escáner de códigos (getUserMedia + BarcodeDetector en el WebView).
//   - NFC: lectura de etiquetas vía Web NFC (scannerHardware.ts).
// Ambos marcados como features opcionales para no excluir dispositivos sin
// cámara/NFC en Play Store.
//
// Uso: node scripts/patch-android-manifest.mjs   (tras `cap add android`/`cap sync`)
import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

const root = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const manifestPath = path.join(root, 'android', 'app', 'src', 'main', 'AndroidManifest.xml');

if (!fs.existsSync(manifestPath)) {
  console.error(`[patch-android] No existe ${manifestPath}. Corre antes: npx cap add android`);
  process.exit(1);
}

const ADDITIONS = `    <uses-permission android:name="android.permission.CAMERA" />
    <uses-permission android:name="android.permission.NFC" />
    <uses-feature android:name="android.hardware.camera" android:required="false" />
    <uses-feature android:name="android.hardware.camera.autofocus" android:required="false" />
    <uses-feature android:name="android.hardware.nfc" android:required="false" />`;

let manifest = fs.readFileSync(manifestPath, 'utf8');

if (manifest.includes('android.permission.CAMERA')) {
  console.log('[patch-android] Manifest ya parcheado — nada que hacer.');
  process.exit(0);
}

const anchor = '<uses-permission android:name="android.permission.INTERNET" />';
if (!manifest.includes(anchor)) {
  console.error('[patch-android] No se encontró el permiso INTERNET de anclaje; revisar manifest.');
  process.exit(1);
}

manifest = manifest.replace(anchor, `${anchor}\n${ADDITIONS}`);
fs.writeFileSync(manifestPath, manifest);
console.log('[patch-android] Permisos CAMERA/NFC agregados al AndroidManifest.xml.');
