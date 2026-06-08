// Perfil de producto del build (ADR-008 / Plan D — Fase D4).
//
// El mismo código fuente se empaqueta en dos sabores según VITE_APP_PROFILE:
//   - 'full'      (default): el ERP completo.
//   - 'cobranza'  : standalone de Cobranza — solo {cxc, core, finanzas, auth,
//                   i18n, integraciones, configuracion}. Sin ventas, inventario,
//                   fiscal ni escáner.
//
// Se construye con:  npm run build:cobranza   (vite --mode cobranza → .env.cobranza)

export type AppProfile = 'full' | 'cobranza';

export function getAppProfile(): AppProfile {
  const raw = (import.meta.env.VITE_APP_PROFILE ?? '').toString().toLowerCase();
  return raw === 'cobranza' ? 'cobranza' : 'full';
}

// Módulos (ids de NavSection y de grupos de rutas) habilitados en el perfil
// 'cobranza'. Imprescindibles del standalone: core (empresas/usuarios), finanzas,
// cobranza (cxc), integraciones y configuración. El panel SaaS se mantiene para
// el proveedor (se sigue protegiendo por rol). Todo lo demás queda fuera.
const COBRANZA_MODULES: ReadonlySet<string> = new Set([
  'inicio',
  'dashboard',
  'cobranza',
  'finanzas',
  'empresas',
  'usuarios',
  'configuracion',
  'integraciones',
  'admin-saas',
]);

/** True si el módulo está habilitado en el perfil de build actual. */
export function isModuleEnabled(moduleId: string): boolean {
  return getAppProfile() === 'full' || COBRANZA_MODULES.has(moduleId);
}

export function isCobranzaStandalone(): boolean {
  return getAppProfile() === 'cobranza';
}
