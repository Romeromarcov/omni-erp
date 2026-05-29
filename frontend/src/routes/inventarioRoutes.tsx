 
import { lazy } from 'react';
import { Route } from 'react-router-dom';

const InventarioDashboardPage = lazy(() => import('../pages/Inventario/InventarioDashboardPage'));
const StockActualPage = lazy(() => import('../pages/Inventario/StockActualPage'));
const KardexPage = lazy(() => import('../pages/Inventario/KardexPage'));
const AjusteInventarioPage = lazy(() => import('../pages/Inventario/AjusteInventarioPage'));

export function inventarioRoutes() {
  return (
    <>
      <Route path="/inventario" element={<InventarioDashboardPage />} />
      <Route path="/inventario/stock" element={<StockActualPage />} />
      <Route path="/inventario/kardex/:productoId" element={<KardexPage />} />
      <Route path="/inventario/ajustes" element={<AjusteInventarioPage />} />
    </>
  );
}
