 
import { lazy } from 'react';
import { Route } from 'react-router-dom';

const DashboardCxCPage = lazy(() => import('../pages/CxC/DashboardCxCPage'));
const CobranzaPage = lazy(() => import('../pages/CxC/CobranzaPage'));
const CuentasPorCobrarPage = lazy(() => import('../pages/CxC/CuentasPorCobrarPage'));
const AcuerdosPage = lazy(() => import('../pages/CxC/AcuerdosPage'));
const AgenteCobranzaPage = lazy(() => import('../pages/CxC/AgenteCobranzaPage'));

export function cxcRoutes() {
  return (
    <>
      <Route path="/cobranza/dashboard" element={<DashboardCxCPage />} />
      <Route path="/cobranza/cuentas" element={<CuentasPorCobrarPage />} />
      <Route path="/cobranza/gestiones" element={<CobranzaPage />} />
      <Route path="/cobranza/acuerdos" element={<AcuerdosPage />} />
      <Route path="/cobranza/agente" element={<AgenteCobranzaPage />} />
    </>
  );
}
