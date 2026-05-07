import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import LoginForm from '../../../components/LoginForm';
import { DeviceActionModal } from '../../../components/DeviceActionModal';
import { get } from '../../../services/api';
import { useAuth } from '../../../contexts/AuthContext';
import type { DispositivoInfo } from '../../../types/dispositivos';
import { Button } from '@mui/material';


const LoginPage: React.FC = () => {
  const navigate = useNavigate();
  const { login, setDispositivoInfo: setAuthDispositivoInfo } = useAuth();
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [empresa, setEmpresa] = useState<string>('');
  const [sucursal, setSucursal] = useState('');
  const [empresas, setEmpresas] = useState<Array<{ id_empresa: string; nombre_legal: string; nombre_comercial?: string }>>([]);
  const [sucursales, setSucursales] = useState<Array<{ id_sucursal: string; nombre: string; id_empresa: string }>>([]);
  const [step, setStep] = useState<'login' | 'select'>('login');
  const [dispositivoInfo, setDispositivoInfo] = useState<DispositivoInfo | null>(null);
  const [showDeviceModal, setShowDeviceModal] = useState(false);

  // Solicita la cookie CSRF al cargar la página de login
  useEffect(() => {
    // Limpiar cualquier token inválido al cargar la página de login
    localStorage.removeItem('token');
    localStorage.removeItem('usuario');
    localStorage.removeItem('empresa');
    localStorage.removeItem('sucursal');
    localStorage.removeItem('id_empresa');
    localStorage.removeItem('id_sucursal');
    localStorage.removeItem('roles');
    localStorage.removeItem('permisos');
    localStorage.removeItem('dispositivo_info');

    // No necesitamos obtener cookie CSRF ya que usamos JWT
    // Si necesitamos verificar conectividad, podemos hacer una petición simple
    // get('/core/empresas/?limit=1').catch(() => {});
  }, []);


  const handleLogin = async (username: string, password: string) => {
    setLoading(true);
    setError('');
    try {
      const dispositivoResult = await login(username, password);

      // Si hay información de dispositivo, verificar la acción
      if (dispositivoResult) {
        setDispositivoInfo(dispositivoResult);
        
        // Si la acción es automática o ya hay sesión activa, ir directamente al dashboard
        if (dispositivoResult.accion === 'abrir_sesion_automatico' || dispositivoResult.accion === 'sesion_activa') {
          // Actualizar la información del dispositivo en el AuthContext si hay sesión abierta
          if (dispositivoResult.sesion_abierta) {
            setAuthDispositivoInfo(dispositivoResult);
            localStorage.setItem('dispositivo_info', JSON.stringify(dispositivoResult));
          }
          navigate('/dashboard');
          setLoading(false);
          return;
        }
        
        // Para otras acciones, continuar con el flujo normal
      }

      // Después de login, siempre cargar empresas y sucursales para selección
      const empresasRes = await get('/core/empresas/');
      let empresasList: Array<{ id_empresa: string; nombre_legal: string; nombre_comercial?: string }> = [];
      if (Array.isArray(empresasRes)) empresasList = empresasRes;
      else if (empresasRes && typeof empresasRes === 'object' && 'results' in empresasRes && Array.isArray((empresasRes as { results: unknown }).results)) {
        empresasList = (empresasRes as { results: Array<{ id_empresa: string; nombre_legal: string; nombre_comercial?: string }> }).results;
      }
      setEmpresas(empresasList);

      const sucursalesRes = await get('/core/sucursales/');
      let sucursalesList: Array<{ id_sucursal: string; nombre: string; id_empresa: string }> = [];
      if (Array.isArray(sucursalesRes)) sucursalesList = sucursalesRes;
      else if (sucursalesRes && typeof sucursalesRes === 'object' && 'results' in sucursalesRes && Array.isArray((sucursalesRes as { results: unknown }).results)) {
        sucursalesList = (sucursalesRes as { results: Array<{ id_sucursal: string; nombre: string; id_empresa: string }> }).results;
      }
      setSucursales(sucursalesList);

      // Ir al paso de selección
      setStep('select');
    } catch (err: unknown) {
      console.error('Login error:', err);
      let errorMsg = 'Credenciales inválidas';
      try {
        const parsed = JSON.parse((err as Error).message);
        if (parsed && parsed.error) errorMsg = parsed.error;
      } catch { /* no-op */ }
      setError(errorMsg);
    } finally {
      setLoading(false);
    }
  };

  const cardStyle: React.CSSProperties = {
    width: '100%',
    maxWidth: 380,
    background: '#fff',
    borderRadius: 16,
    boxShadow: '0 4px 24px rgba(0,0,0,0.08)',
    padding: '32px 24px',
    margin: '16px',
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
  };



  const handleDeviceActionComplete = (success: boolean, updatedDispositivoInfo?: DispositivoInfo) => {
    setShowDeviceModal(false);

    if (success && updatedDispositivoInfo) {
      // Actualizar la información del dispositivo en el AuthContext
      setAuthDispositivoInfo(updatedDispositivoInfo);
      localStorage.setItem('dispositivo_info', JSON.stringify(updatedDispositivoInfo));

      // Después de completar la acción del dispositivo, ir al dashboard
      navigate('/dashboard');
    } else {
      // Si falló, mostrar error pero permitir continuar
      setError('Error procesando acción del dispositivo. Puede continuar normalmente.');
      navigate('/dashboard');
    }
  };

  const handleDeviceModalClose = () => {
    setShowDeviceModal(false);
    // Al cerrar el modal, continuar al dashboard
    navigate('/dashboard');
  };

  // Si hay que mostrar el modal de dispositivo, renderizarlo sobre la interfaz
  const renderDeviceModal = () => {
    if (showDeviceModal && dispositivoInfo) {
      return (
        <DeviceActionModal
          dispositivoInfo={dispositivoInfo}
          onActionComplete={handleDeviceActionComplete}
          onClose={handleDeviceModalClose}
        />
      );
    }
    return null;
  };

  return (
    <div className="vertical-center">
      <div className="centered-container" style={{ background: 'linear-gradient(135deg, #e3f0ff 0%, #f6fafd 100%)' }}>
        <div style={cardStyle}>
          {step === 'login' && (
            <>
              <h2 style={{ textAlign: 'center', marginBottom: 8, color: '#1976d2' }}>Iniciar sesión</h2>
              <LoginForm onSubmit={handleLogin} loading={loading} error={error} />
            </>
          )}
          {step === 'select' && (
            <form
              onSubmit={e => {
                e.preventDefault();
                if (empresa) {
                  const empresaObj = empresas.find(emp => String(emp.id_empresa) === String(empresa));
                  if (empresaObj) {
                    localStorage.setItem('empresa', JSON.stringify(empresaObj));
                    localStorage.setItem('id_empresa', empresaObj.id_empresa);
                  }
                }
                if (sucursal) {
                  const sucursalObj = sucursales.find(suc => String(suc.id_sucursal) === String(sucursal));
                  if (sucursalObj) {
                    localStorage.setItem('sucursal', JSON.stringify(sucursalObj));
                  }
                }
                if (dispositivoInfo && (dispositivoInfo.accion === 'preguntar_caja' || dispositivoInfo.accion === 'abrir_sesion')) {
                  setShowDeviceModal(true);
                } else {
                  navigate('/dashboard');
                }
              }}
              style={{ maxWidth: 350, margin: '0 auto', display: 'flex', flexDirection: 'column', gap: 16 }}
            >
              <h3 style={{ textAlign: 'center', color: '#1976d2' }}>Selecciona empresa y sucursal (opcional)</h3>
              <label>Empresa</label>
              <select value={empresa} onChange={e => { setEmpresa(e.target.value); }}>
                <option value="">Seleccione una empresa</option>
                {(Array.isArray(empresas) ? empresas : []).map(emp => (
                  <option key={emp.id_empresa} value={String(emp.id_empresa)}>{emp.nombre_legal}</option>
                ))}
              </select>
              <label>Sucursal</label>
              <select value={sucursal} onChange={e => setSucursal(e.target.value)} disabled={!empresa}>
                <option value="">Seleccione una sucursal</option>
                {sucursales
                  .filter(suc => suc && String(suc.id_empresa) === String(empresa))
                  .map(suc => (
                    <option key={`${suc.id_sucursal}-${suc.nombre}`} value={suc.id_sucursal}>{suc.nombre}</option>
                  ))
                }
              </select>
              <Button type="submit">Continuar</Button>
            </form>
          )}
        </div>
      </div>
      {renderDeviceModal()}
    </div>
  );
};

export default LoginPage;