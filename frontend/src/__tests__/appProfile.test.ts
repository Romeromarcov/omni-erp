import { describe, it, expect, afterEach, vi } from 'vitest';
import { getAppProfile, isModuleEnabled, isCobranzaStandalone } from '../config/appProfile';

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
