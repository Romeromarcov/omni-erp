import { lazy } from 'react';
import { Route } from 'react-router-dom';

const GastosPage = lazy(() => import('../pages/Gastos/GastosPage'));
const CategoriasGastoPage = lazy(() => import('../pages/Gastos/CategoriasGastoPage'));
const ReembolsosPage = lazy(() => import('../pages/Gastos/ReembolsosPage'));

export function gastosRoutes() {
  return (
    <>
      <Route path="/gastos" element={<GastosPage />} />
      <Route path="/gastos/categorias" element={<CategoriasGastoPage />} />
      <Route path="/gastos/reembolsos" element={<ReembolsosPage />} />
    </>
  );
}
