/**
 * Acceso a hardware de escaneo con detección de capacidades y degradación
 * elegante. Funciona en:
 *  - Web/PWA y Android (WebView Chromium): cámara vía getUserMedia + BarcodeDetector.
 *  - NFC: Web NFC (NDEFReader) en Android Chrome.
 *  - Donde no haya soporte (p. ej. iOS Safari): el llamador cae al lector manual.
 *
 * El plugin nativo de Capacitor (ML Kit) puede enchufarse aquí más adelante para
 * iOS sin cambiar la UI; el contrato (startCameraScan / readNfcOnce) se mantiene.
 */

// ── Tipos ambientales mínimos (no están en lib.dom estándar) ──────────────────
interface DetectedBarcode {
  rawValue: string;
  format: string;
}
interface BarcodeDetectorLike {
  detect: (source: CanvasImageSource) => Promise<DetectedBarcode[]>;
}
interface BarcodeDetectorCtor {
  new (opts?: { formats?: string[] }): BarcodeDetectorLike;
  getSupportedFormats?: () => Promise<string[]>;
}
interface NDEFReadingEventLike {
  serialNumber?: string;
  message?: { records: Array<{ recordType: string; data?: BufferSource }> };
}
interface NDEFReaderLike {
  scan: (opts?: { signal?: AbortSignal }) => Promise<void>;
  addEventListener: (type: 'reading' | 'readingerror', cb: (ev: NDEFReadingEventLike) => void) => void;
}

function getBarcodeDetectorCtor(): BarcodeDetectorCtor | undefined {
  return (globalThis as unknown as { BarcodeDetector?: BarcodeDetectorCtor }).BarcodeDetector;
}

export function isCameraScanSupported(): boolean {
  return (
    typeof navigator !== 'undefined' &&
    !!navigator.mediaDevices?.getUserMedia &&
    !!getBarcodeDetectorCtor()
  );
}

export function isNfcSupported(): boolean {
  return typeof window !== 'undefined' && 'NDEFReader' in window;
}

/** Formatos por modo del escáner. */
const FORMATS: Record<'barcode' | 'qr', string[]> = {
  barcode: ['ean_13', 'ean_8', 'code_128', 'code_39', 'upc_a', 'upc_e', 'itf', 'codabar'],
  qr: ['qr_code', 'data_matrix', 'aztec', 'pdf417'],
};

export interface CameraScanHandle {
  stop: () => void;
}

/**
 * Inicia la cámara trasera y detecta códigos en bucle. Llama `onResult` con el
 * primer código leído (luego deja de notificar; el llamador decide detener).
 * Devuelve un handle con `stop()` para liberar la cámara.
 */
export async function startCameraScan(
  video: HTMLVideoElement,
  mode: 'barcode' | 'qr',
  onResult: (code: string) => void,
  onError?: (err: unknown) => void,
): Promise<CameraScanHandle> {
  const Ctor = getBarcodeDetectorCtor();
  if (!Ctor || !navigator.mediaDevices?.getUserMedia) {
    throw new Error('La detección por cámara no está soportada en esta plataforma.');
  }

  let stream: MediaStream | null = null;
  let raf = 0;
  let stopped = false;
  let delivered = false;
  const detector = new Ctor({ formats: FORMATS[mode] });

  const stop = () => {
    stopped = true;
    if (raf) cancelAnimationFrame(raf);
    if (stream) stream.getTracks().forEach((t) => t.stop());
    stream = null;
  };

  try {
    stream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: { ideal: 'environment' } },
      audio: false,
    });
    video.srcObject = stream;
    video.setAttribute('playsinline', 'true');
    await video.play();

    const tick = async () => {
      if (stopped || delivered) return;
      try {
        const codes = await detector.detect(video);
        if (codes.length > 0 && codes[0].rawValue) {
          delivered = true;
          onResult(codes[0].rawValue);
          return;
        }
      } catch {
        /* frame no analizable; reintenta en el próximo */
      }
      raf = requestAnimationFrame(() => void tick());
    };
    raf = requestAnimationFrame(() => void tick());
  } catch (err) {
    stop();
    if (onError) onError(err);
    throw err;
  }

  return { stop };
}

/** Lee una etiqueta NFC una sola vez (Web NFC, Android Chrome). */
export async function readNfcOnce(signal?: AbortSignal): Promise<string> {
  const Ctor = (window as unknown as { NDEFReader?: new () => NDEFReaderLike }).NDEFReader;
  if (!Ctor) throw new Error('Web NFC no está soportado en esta plataforma.');
  const reader = new Ctor();
  return new Promise<string>((resolve, reject) => {
    reader.addEventListener('reading', (ev) => {
      resolve(ev.serialNumber || 'NFC');
    });
    reader.addEventListener('readingerror', () => reject(new Error('No se pudo leer la etiqueta NFC.')));
    reader.scan({ signal }).catch(reject);
  });
}
