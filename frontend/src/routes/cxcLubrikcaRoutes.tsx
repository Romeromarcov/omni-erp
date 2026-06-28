import { lazy } from 'react';
import { Route } from 'react-router-dom';

const DashboardCxcLubrikcaPage = lazy(
  () => import('../pages/CxcLubrikca/DashboardCxcLubrikcaPage'),
);
const ConfigMotorPage = lazy(() => import('../pages/CxcLubrikca/ConfigMotorPage'));
const CapturaPage = lazy(() => import('../pages/CxcLubrikca/CapturaPage'));
const BandejaPage = lazy(() => import('../pages/CxcLubrikca/BandejaPage'));
const ConciliacionPage = lazy(() => import('../pages/CxcLubrikca/ConciliacionPage'));
const CarteraPage = lazy(() => import('../pages/CxcLubrikca/CarteraPage'));

/**
 * Rutas del subproyecto CxC Lubrikca (perfil 'cobranza').
 *
 * Fase 6a: Dashboard y Config del Motor.
 * Fase 6b: Captura, Bandeja, Conciliación y Cartera.
 */
export function cxcLubrikcaRoutes() {
  return (
    <>
      <Route path="/cxc-lubrikca/dashboard" element={<DashboardCxcLubrikcaPage />} />
      <Route path="/cxc-lubrikca/config" element={<ConfigMotorPage />} />
      <Route path="/cxc-lubrikca/captura" element={<CapturaPage />} />
      <Route path="/cxc-lubrikca/bandeja" element={<BandejaPage />} />
      <Route path="/cxc-lubrikca/conciliacion" element={<ConciliacionPage />} />
      <Route path="/cxc-lubrikca/cartera" element={<CarteraPage />} />
    </>
  );
}
