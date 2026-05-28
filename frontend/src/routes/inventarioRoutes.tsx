import { Route } from 'react-router-dom';
import InventarioDashboardPage from '../pages/Inventario/InventarioDashboardPage';
import StockActualPage from '../pages/Inventario/StockActualPage';
import KardexPage from '../pages/Inventario/KardexPage';
import AjusteInventarioPage from '../pages/Inventario/AjusteInventarioPage';

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
