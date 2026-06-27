import { lazy } from 'react';
import { Route } from 'react-router-dom';

const MovimientosBancariosPage = lazy(() => import('../pages/Tesoreria/MovimientosBancariosPage'));
const ConciliacionesListPage = lazy(() => import('../pages/Tesoreria/ConciliacionesListPage'));
const ConciliacionDetailPage = lazy(() => import('../pages/Tesoreria/ConciliacionDetailPage'));
const OperacionesCambioListPage = lazy(() => import('../pages/Tesoreria/OperacionesCambioListPage'));
const OperacionCambioFormPage = lazy(() => import('../pages/Tesoreria/OperacionCambioFormPage'));
const MovimientosInternosFondoPage = lazy(() => import('../pages/Tesoreria/MovimientosInternosFondoPage'));

export function tesoreriaRoutes() {
  return (
    <>
      <Route path="/tesoreria/movimientos-bancarios" element={<MovimientosBancariosPage />} />
      <Route path="/tesoreria/conciliaciones" element={<ConciliacionesListPage />} />
      <Route path="/tesoreria/conciliaciones/:id" element={<ConciliacionDetailPage />} />
      <Route path="/tesoreria/cambio-divisa" element={<OperacionesCambioListPage />} />
      <Route path="/tesoreria/cambio-divisa/nueva" element={<OperacionCambioFormPage />} />
      <Route path="/tesoreria/movimientos-internos" element={<MovimientosInternosFondoPage />} />
    </>
  );
}
