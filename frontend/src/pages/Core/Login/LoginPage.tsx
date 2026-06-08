import React, { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import LoginForm from '../../../components/LoginForm';
import { DeviceActionModal } from '../../../components/DeviceActionModal';
import { get } from '../../../services/api';
import { useAuth } from '../../../contexts/AuthContext';
import type { DispositivoInfo } from '../../../types/dispositivos';
import { Box, Button, FormControl, InputLabel, Select, MenuItem, Typography } from '@mui/material';
import { BrandMark, Wordmark } from '../../../components/ui';


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

  // Al cargar la página de login, limpiar la selección de UI persistida.
  // FE-HIGH-13: tokens/PII ya no viven en localStorage (están en memoria); solo
  // quedan las selecciones no sensibles id_empresa/id_sucursal.
  useEffect(() => {
    localStorage.removeItem('id_empresa');
    localStorage.removeItem('id_sucursal');
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
    maxWidth: 400,
    background: '#fff',
    borderRadius: 20,
    boxShadow: '0 12px 40px rgba(16,42,80,0.12)',
    border: '1px solid rgba(16,42,80,0.06)',
    padding: '34px 28px',
    margin: '16px',
    display: 'flex',
    flexDirection: 'column',
    gap: 16,
    position: 'relative',
    zIndex: 1,
  };



  const handleDeviceActionComplete = (success: boolean, updatedDispositivoInfo?: DispositivoInfo) => {
    setShowDeviceModal(false);

    if (success && updatedDispositivoInfo) {
      // Actualizar la información del dispositivo en el AuthContext
      setAuthDispositivoInfo(updatedDispositivoInfo);

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
      <div
        className="centered-container"
        style={{
          background: 'linear-gradient(135deg, #e3f0ff 0%, #f6fafd 100%)',
          position: 'relative',
          overflow: 'hidden',
        }}
      >
        {/* Fondo orbital decorativo */}
        <svg
          aria-hidden
          viewBox="0 0 420 880"
          preserveAspectRatio="xMidYMid slice"
          style={{ position: 'absolute', inset: 0, width: '100%', height: '100%', pointerEvents: 'none' }}
        >
          <g fill="none" stroke="#1976d2" strokeWidth="1">
            <circle cx="360" cy="120" r="90" opacity=".10" />
            <circle cx="360" cy="120" r="150" opacity=".07" />
            <circle cx="60" cy="760" r="110" opacity=".09" />
            <circle cx="60" cy="760" r="180" opacity=".06" />
          </g>
          <circle cx="420" cy="120" r="6" fill="#42a5f5" opacity=".6" />
          <circle cx="20" cy="760" r="5" fill="#7c4dff" opacity=".6" />
        </svg>

        <div style={cardStyle}>
          {step === 'login' && (
            <>
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1.25, mb: 1 }}>
                <BrandMark size={56} />
                <Wordmark size={26} />
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center' }}>
                  Gestión empresarial integral · multimoneda
                </Typography>
              </Box>
              <Typography variant="h6" sx={{ textAlign: 'center' }}>
                Iniciar sesión
              </Typography>
              <LoginForm onSubmit={handleLogin} loading={loading} error={error} />
              <Button variant="text" fullWidth onClick={() => navigate('/signup')} disabled={loading}>
                ¿No tienes cuenta? Regístrate gratis
              </Button>
            </>
          )}
          {step === 'select' && (
            <form
              onSubmit={e => {
                e.preventDefault();
                if (empresa) {
                  const empresaObj = empresas.find(emp => String(emp.id_empresa) === String(empresa));
                  if (empresaObj) {
                    // Solo la selección de UI (no PII) se persiste.
                    localStorage.setItem('id_empresa', empresaObj.id_empresa);
                  }
                }
                if (sucursal) {
                  const sucursalObj = sucursales.find(suc => String(suc.id_sucursal) === String(sucursal));
                  if (sucursalObj) {
                    localStorage.setItem('id_sucursal', sucursalObj.id_sucursal);
                  }
                }
                if (dispositivoInfo && (dispositivoInfo.accion === 'preguntar_caja' || dispositivoInfo.accion === 'abrir_sesion')) {
                  setShowDeviceModal(true);
                } else {
                  navigate('/dashboard');
                }
              }}
              style={{ display: 'flex', flexDirection: 'column', gap: 16 }}
            >
              <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 1, mb: 1 }}>
                <BrandMark size={44} />
                <Typography variant="h6" sx={{ textAlign: 'center' }}>
                  Selecciona empresa y sucursal
                </Typography>
                <Typography variant="body2" color="text.secondary" sx={{ textAlign: 'center' }}>
                  Tu sesión se abrirá en este contexto
                </Typography>
              </Box>
              <FormControl fullWidth size="small">
                <InputLabel>Empresa</InputLabel>
                <Select value={empresa} label="Empresa" onChange={e => setEmpresa(e.target.value)}>
                  <MenuItem value=""><em>Seleccione una empresa</em></MenuItem>
                  {(Array.isArray(empresas) ? empresas : []).map(emp => (
                    <MenuItem key={emp.id_empresa} value={String(emp.id_empresa)}>{emp.nombre_legal}</MenuItem>
                  ))}
                </Select>
              </FormControl>
              <FormControl fullWidth size="small" disabled={!empresa}>
                <InputLabel>Sucursal</InputLabel>
                <Select value={sucursal} label="Sucursal" onChange={e => setSucursal(e.target.value)}>
                  <MenuItem value=""><em>Seleccione una sucursal</em></MenuItem>
                  {sucursales
                    .filter(suc => suc && String(suc.id_empresa) === String(empresa))
                    .map(suc => (
                      <MenuItem key={`${suc.id_sucursal}-${suc.nombre}`} value={suc.id_sucursal}>{suc.nombre}</MenuItem>
                    ))
                  }
                </Select>
              </FormControl>
              <Button type="submit" variant="contained" fullWidth>Continuar</Button>
            </form>
          )}
        </div>
      </div>
      {renderDeviceModal()}
    </div>
  );
};

export default LoginPage;