import React, { createContext, useContext, useState, useEffect, useCallback } from 'react';
import type { Usuario } from '../services/users';
import type { DispositivoInfo } from '../types/dispositivos';
import { loginAndFetchUser } from '../services/auth';

interface AuthContextType {
  user: Usuario | null;
  token: string | null;
  cajaFisica: { id_caja_fisica: string; nombre: string; tipo_caja: string } | null;
  dispositivoInfo: DispositivoInfo | null;
  isLoading: boolean;
  login: (username: string, password: string) => Promise<DispositivoInfo | null>;
  logout: () => void;
  refreshUser: () => Promise<void>;
  setDispositivoInfo: (info: DispositivoInfo | null) => void;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export const AuthProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [user, setUser] = useState<Usuario | null>(null);
  const [token, setToken] = useState<string | null>(localStorage.getItem('token'));
  const [cajaFisica, setCajaFisica] = useState<{ id_caja_fisica: string; nombre: string; tipo_caja: string } | null>(null);
  const [dispositivoInfo, setDispositivoInfo] = useState<DispositivoInfo | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const refreshUser = useCallback(async () => {
    if (!token) return;
    try {
      const storedUser = localStorage.getItem('usuario');
      const storedCajaFisica = localStorage.getItem('caja_fisica');
      const storedDispositivoInfo = localStorage.getItem('dispositivo_info');
      if (storedUser) {
        setUser(JSON.parse(storedUser));
      }
      if (storedCajaFisica) {
        setCajaFisica(JSON.parse(storedCajaFisica));
      }
      if (storedDispositivoInfo) {
        setDispositivoInfo(JSON.parse(storedDispositivoInfo));
      }
    } catch {
      setToken(null);
      setUser(null);
      setCajaFisica(null);
      setDispositivoInfo(null);
      localStorage.clear();
    }
  }, [token]);

  useEffect(() => {
    if (token && !user) {
      refreshUser();
    }
  }, [token, user, refreshUser]);

  const login = async (username: string, password: string): Promise<DispositivoInfo | null> => {
    setIsLoading(true);
    try {
      const { token: newToken, refresh, usuario, dispositivo } = await loginAndFetchUser(username, password);
      setToken(newToken);
      setUser(usuario);
      setDispositivoInfo(dispositivo || null);

      // Guardar información de dispositivo si existe
      if (dispositivo) {
        localStorage.setItem('dispositivo_info', JSON.stringify(dispositivo));
      }

      // Si se abrió sesión automáticamente, actualizar caja física
      if (dispositivo?.sesion_abierta) {
        setCajaFisica({
          id_caja_fisica: dispositivo.sesion_abierta.caja_fisica.id_caja_fisica,
          nombre: dispositivo.sesion_abierta.caja_fisica.nombre,
          tipo_caja: 'VENTA' // Valor por defecto, se puede obtener del backend si es necesario
        });
        localStorage.setItem('caja_fisica', JSON.stringify({
          id_caja_fisica: dispositivo.sesion_abierta.caja_fisica.id_caja_fisica,
          nombre: dispositivo.sesion_abierta.caja_fisica.nombre,
          tipo_caja: 'VENTA'
        }));
      }

      localStorage.setItem('token', newToken);
      if (refresh) {
        localStorage.setItem('refresh_token', refresh);
      }
      localStorage.setItem('usuario', JSON.stringify(usuario));
      if (usuario.empresas && usuario.empresas.length > 0) {
        localStorage.setItem('empresa', JSON.stringify(usuario.empresas[0]));
        localStorage.setItem('id_empresa', usuario.empresas[0].id_empresa);
      }
      if (usuario.sucursales && usuario.sucursales.length > 0) {
        localStorage.setItem('sucursal', JSON.stringify(usuario.sucursales[0]));
        localStorage.setItem('id_sucursal', usuario.sucursales[0].id_sucursal);
      }

      return dispositivo || null;
    } finally {
      setIsLoading(false);
    }
  };

  const logout = useCallback(() => {
    setToken(null);
    setUser(null);
    setCajaFisica(null);
    setDispositivoInfo(null);
    localStorage.clear();
  }, []);

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
