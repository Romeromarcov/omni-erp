// Context files intentionally export both the provider component and the hook.
// react-refresh/only-export-components is a dev-HMR concern; does not affect production.
/* eslint-disable react-refresh/only-export-components */
import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { Usuario } from '../services/users';
import type { DispositivoInfo } from '../types/dispositivos';
import { loginAndFetchUser, hydrateSession, logoutSession } from '../services/auth';
import {
  getAccessToken,
  setUnauthorizedHandler,
} from '../services/api';
import {
  setSessionDispositivoInfo,
  setSessionCajaFisica,
  clearSession,
  type CajaFisicaSel,
} from '../services/session';
import { queryClient } from '../lib/queryClient';
import { clearPersistedQueryCache } from '../lib/idbPersister';

interface AuthContextType {
  user: Usuario | null;
  token: string | null;
  cajaFisica: CajaFisicaSel | null;
  dispositivoInfo: DispositivoInfo | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<DispositivoInfo | null>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  setDispositivoInfo: (info: DispositivoInfo | null) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

// FE-HIGH-13 migration shim: remove any legacy token/PII left in localStorage
// by previous versions. Only non-PII UI selection keys are allowed to remain.
function purgeLegacyAuthStorage(): void {
  ['token', 'usuario', 'empresa', 'sucursal', 'roles', 'permisos', 'id_usuario',
    'caja_fisica', 'dispositivo_info'].forEach((k) => localStorage.removeItem(k));
}

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<Usuario | null>(null);
  // Token lives in api.ts memory; this is a render-trigger mirror only.
  const [token, setTokenState] = useState<string | null>(null);
  const [cajaFisica, setCajaFisicaState] = useState<CajaFisicaSel | null>(null);
  const [dispositivoInfo, setDispositivoInfoState] = useState<DispositivoInfo | null>(null);
  // Start in loading state: on mount we attempt to rehydrate from the refresh cookie.
  const [isLoading, setIsLoading] = useState(true);

  const setDispositivoInfo = useCallback((info: DispositivoInfo | null) => {
    setSessionDispositivoInfo(info);
    setDispositivoInfoState(info);
  }, []);

  const logout = useCallback(() => {
    logoutSession();
    setTokenState(null);
    setUser(null);
    setCajaFisicaState(null);
    setDispositivoInfoState(null);
    clearSession();
    // Drop UI selection too — it is per-session and may leak across users.
    localStorage.removeItem('id_empresa');
    localStorage.removeItem('id_sucursal');
    // Offline réplica local (CTF-008): purgar el caché de negocio en memoria y
    // su réplica en IndexedDB para que los datos de un tenant/usuario no queden
    // disponibles para el siguiente en un dispositivo compartido (R-CODE-1).
    queryClient.clear();
    void clearPersistedQueryCache();
  }, []);

  const refreshUser = useCallback(async () => {
    const hydrated = await hydrateSession();
    if (hydrated) {
      setUser(hydrated);
      setTokenState(getAccessToken());
    } else {
      logout();
    }
  }, [logout]);

  // FE-HIGH-11/13: wire the api layer's unauthorized handler to context logout.
  useEffect(() => {
    setUnauthorizedHandler(() => {
      logout();
      if (typeof window !== 'undefined' && !window.location.pathname.startsWith('/login')) {
        window.location.href = '/login';
      }
    });
    return () => setUnauthorizedHandler(null);
  }, [logout]);

  // On mount: purge legacy storage and try to rehydrate via the refresh cookie.
  useEffect(() => {
    let cancelled = false;
    purgeLegacyAuthStorage();
    (async () => {
      const hydrated = await hydrateSession();
      if (cancelled) return;
      if (hydrated) {
        setUser(hydrated);
        setTokenState(getAccessToken());
      }
      setIsLoading(false);
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  const login = async (username: string, password: string): Promise<DispositivoInfo | null> => {
    // OJO: NO tocar `isLoading` aquí. Ese flag protege solo la rehidratación
    // inicial; mientras está en true AppRouter desmonta el árbol completo
    // (incluida LoginPage), lo que reseteaba el paso de selección de
    // empresa/sucursal tras el login (bug detectado por el E2E de TEST-6).
    // El spinner del formulario lo maneja LoginPage con su estado local.
    // SEC-03: `refresh` is no longer returned — it arrives as an httpOnly cookie.
    const { token: newToken, usuario, dispositivo } = await loginAndFetchUser(username, password);
    setTokenState(newToken);
    setUser(usuario);

    if (dispositivo) {
      setDispositivoInfo(dispositivo);
    }

    // Si se abrió sesión automáticamente, actualizar caja física (en memoria).
    if (dispositivo?.sesion_abierta) {
      const caja: CajaFisicaSel = {
        id_caja_fisica: dispositivo.sesion_abierta.caja_fisica.id_caja_fisica,
        nombre: dispositivo.sesion_abierta.caja_fisica.nombre,
        tipo_caja: 'VENTA',
      };
      setSessionCajaFisica(caja);
      setCajaFisicaState(caja);
    }

    // UI selection (non-PII) — first empresa/sucursal as defaults.
    if (usuario.empresas && usuario.empresas.length > 0) {
      localStorage.setItem('id_empresa', usuario.empresas[0].id_empresa);
    }
    if (usuario.sucursales && usuario.sucursales.length > 0) {
      localStorage.setItem('id_sucursal', usuario.sucursales[0].id_sucursal);
    }

    return dispositivo || null;
  };

  return (
    <AuthContext.Provider value={{ user, token, cajaFisica, dispositivoInfo, isLoading, login, logout, refreshUser, setDispositivoInfo }}>
      {children}
    </AuthContext.Provider>
  );
};

export const useAuth = () => {
  const context = useContext(AuthContext);
  if (!context) {
    throw new Error('useAuth must be used within AuthProvider');
  }
  return context;
};
