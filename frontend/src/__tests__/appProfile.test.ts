import { describe, it, expect, afterEach, vi } from 'vitest';
import {
  getAppProfile,
  isModuleEnabled,
  isCobranzaStandalone,
  isCxcLubrikcaVisible,
  getCxcLubrikcaEmpresas,
} from '../config/appProfile';

afterEach(() => {
  vi.unstubAllEnvs();
});

describe('appProfile', () => {
  it('por defecto el perfil es full y todo está habilitado', () => {
    expect(getAppProfile()).toBe('full');
    expect(isCobranzaStandalone()).toBe(false);
    expect(isModuleEnabled('ventas')).toBe(true);
    expect(isModuleEnabled('inventario')).toBe(true);
    expect(isModuleEnabled('cobranza')).toBe(true);
  });

  it('con VITE_APP_PROFILE=cobranza recorta los módulos no imprescindibles', () => {
    vi.stubEnv('VITE_APP_PROFILE', 'cobranza');
    expect(getAppProfile()).toBe('cobranza');
    expect(isCobranzaStandalone()).toBe(true);

    // Imprescindibles del standalone
    expect(isModuleEnabled('cobranza')).toBe(true);
    expect(isModuleEnabled('finanzas')).toBe(true);
    expect(isModuleEnabled('empresas')).toBe(true);
    expect(isModuleEnabled('integraciones')).toBe(true);
    expect(isModuleEnabled('admin-saas')).toBe(true);

    // Prescindibles → fuera
    expect(isModuleEnabled('ventas')).toBe(false);
    expect(isModuleEnabled('inventario')).toBe(false);
    expect(isModuleEnabled('fiscal')).toBe(false);
    expect(isModuleEnabled('escaner')).toBe(false);
  });
});

describe('isCxcLubrikcaVisible', () => {
  const LUBRIKCA = '11111111-1111-1111-1111-111111111111';
  const OTRA = '99999999-9999-9999-9999-999999999999';

  it('en build cobranza (standalone Lubrikca) siempre visible', () => {
    vi.stubEnv('VITE_APP_PROFILE', 'cobranza');
    expect(isCxcLubrikcaVisible(OTRA, false)).toBe(true);
    expect(isCxcLubrikcaVisible(null, false)).toBe(true);
  });

  it('en build full: el admin del sistema siempre lo ve', () => {
    expect(isCxcLubrikcaVisible(OTRA, true)).toBe(true);
  });

  it('en build full: solo las empresas de la allowlist lo ven', () => {
    vi.stubEnv('VITE_CXC_LUBRIKCA_EMPRESAS', `${LUBRIKCA}, otra-mas`);
    expect(getCxcLubrikcaEmpresas().has(LUBRIKCA)).toBe(true);
    expect(isCxcLubrikcaVisible(LUBRIKCA, false)).toBe(true);
    expect(isCxcLubrikcaVisible(OTRA, false)).toBe(false);
  });

  it('en build full sin allowlist: ninguna empresa común lo ve', () => {
    expect(isCxcLubrikcaVisible(LUBRIKCA, false)).toBe(false);
    expect(isCxcLubrikcaVisible(null, false)).toBe(false);
  });
});
