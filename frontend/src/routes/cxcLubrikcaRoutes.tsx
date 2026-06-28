import { lazy } from 'react';
import { Route } from 'react-router-dom';

const DashboardCxcLubrikcaPage = lazy(
  () => import('../pages/CxcLubrikca/DashboardCxcLubrikcaPage'),
);
const ConfigMotorPage = lazy(() => import('../pages/CxcLubrikca/ConfigMotorPage'));

/**
 * Rutas del subproyecto CxC Lubrikca (perfil 'cobranza').
 *
 * Fase 6a: solo Dashboard y Config del Motor. Fase 6b añadirá las rutas de
 * captura / bandeja / conciliación / cartera.
 */
export function cxcLubrikcaRoutes() {
  return (
    <>
      <Route path="/cxc-lubrikca/dashboard" element={<DashboardCxcLubrikcaPage />} />
      <Route path="/cxc-lubrikca/config" element={<ConfigMotorPage />} />
    </>
  );
}
