import { lazy } from 'react';
import { Route } from 'react-router-dom';

const PlanCuentasPage = lazy(() => import('../pages/Contabilidad/PlanCuentasPage'));
const DiariosContablesPage = lazy(() => import('../pages/Contabilidad/DiariosContablesPage'));
const AsientosContablesListPage = lazy(() => import('../pages/Contabilidad/AsientosContablesListPage'));
const AsientoContableDetailPage = lazy(() => import('../pages/Contabilidad/AsientoContableDetailPage'));
const MapeosContablesPage = lazy(() => import('../pages/Contabilidad/MapeosContablesPage'));

export function contabilidadRoutes() {
  return (
    <>
      <Route path="/contabilidad/plan-cuentas" element={<PlanCuentasPage />} />
      <Route path="/contabilidad/diarios" element={<DiariosContablesPage initialTab="diarios" />} />
      <Route path="/contabilidad/periodos" element={<DiariosContablesPage initialTab="periodos" />} />
      <Route path="/contabilidad/asientos" element={<AsientosContablesListPage />} />
      <Route path="/contabilidad/asientos/:id" element={<AsientoContableDetailPage />} />
      <Route path="/contabilidad/mapeos" element={<MapeosContablesPage />} />
    </>
  );
}
