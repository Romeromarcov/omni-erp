/**
 * Servicio del módulo de Escáner (código de barras · QR · NFC).
 *
 * Hoy resuelve contra un catálogo de ejemplo (mismas entidades que el
 * prototipo de diseño). El contrato está pensado para sustituir `resolve`
 * por una búsqueda real de inventario / documentos / clientes sin tocar la UI.
 */

export type ScanMode = 'barcode' | 'qr' | 'nfc';

export interface ScanResult {
  /** Código crudo leído (EAN, payload QR, UID NFC…). */
  code: string;
  /** Descripción del tipo de código detectado. */
  kind: string;
  /** Título de la entidad resuelta. */
  title: string;
  /** Subtítulo (SKU, RIF, categoría…). */
  sub: string;
  /** Filas clave/valor a mostrar en la tarjeta de resultado. */
  rows: Array<[string, string]>;
  /** Acción primaria sugerida ("Agregar al pedido", "Abrir documento"…). */
  action: string;
  /** Tipo de entidad resuelta, para enrutar la acción. */
  entity: 'producto' | 'documento' | 'cliente';
}

export interface ScanModeMeta {
  id: ScanMode;
  label: string;
}

export const SCAN_MODES: ScanModeMeta[] = [
  { id: 'barcode', label: 'Código' },
  { id: 'qr', label: 'QR' },
  { id: 'nfc', label: 'NFC' },
];

const SCAN_DB: Record<ScanMode, ScanResult> = {
  barcode: {
    code: '7 591234 008821',
    kind: 'Código de barras (EAN-13)',
    title: 'Café Fama de América 250g',
    sub: 'SKU-1182 · Categoría: Alimentos',
    rows: [
      ['Existencia', '48 und'],
      ['Precio', '$3,90'],
      ['En Bs.', 'Bs. 142,00'],
    ],
    action: 'Agregar al pedido',
    entity: 'producto',
  },
  qr: {
    code: 'OMNI://DOC/FAC-02211',
    kind: 'Código QR · Documento',
    title: 'Factura Fiscal F-02211',
    sub: 'Comercial Andina C.A. · J-30512345-6',
    rows: [
      ['Estado', 'Emitida'],
      ['Total', '$1.240,00'],
      ['Emitida', 'hace 1 h'],
    ],
    action: 'Abrir documento',
    entity: 'documento',
  },
  nfc: {
    code: 'NFC · 04:A3:9B:2C:71',
    kind: 'Etiqueta NFC · Cliente',
    title: 'Distribuidora Mar Azul',
    sub: 'V-12345678-9 · Cliente frecuente',
    rows: [
      ['Cartera', '$3.910,00'],
      ['Mora', '+90 días'],
      ['Riesgo', 'Alto'],
    ],
    action: 'Ver cuenta',
    entity: 'cliente',
  },
};

/** Escaneos recientes de ejemplo (placeholder hasta tener historial real). */
export interface RecentScan {
  entity: ScanResult['entity'];
  title: string;
  code: string;
}

export const RECENT_SCANS: RecentScan[] = [
  { entity: 'producto', title: 'Café Fama 250g', code: 'SKU-1182' },
  { entity: 'documento', title: 'Factura F-02208', code: 'OMNI://DOC' },
  { entity: 'cliente', title: 'Cliente Mar Azul', code: 'NFC·04:A3' },
];

/**
 * Resuelve un código escaneado a una entidad de Omni.
 * `code` se ignora en la implementación de ejemplo; al conectar inventario
 * real se usará para la búsqueda.
 */
export async function resolveScan(mode: ScanMode, _code?: string): Promise<ScanResult> {
  void _code;
  return SCAN_DB[mode];
}
