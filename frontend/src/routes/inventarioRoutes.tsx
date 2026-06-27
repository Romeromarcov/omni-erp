
import { lazy } from 'react';
import { Route } from 'react-router-dom';

const InventarioDashboardPage = lazy(() => import('../pages/Inventario/InventarioDashboardPage'));
const StockActualPage = lazy(() => import('../pages/Inventario/StockActualPage'));
const KardexPage = lazy(() => import('../pages/Inventario/KardexPage'));
const AjusteInventarioPage = lazy(() => import('../pages/Inventario/AjusteInventarioPage'));
const RecepcionesPage = lazy(() => import('../pages/Inventario/RecepcionesPage'));
const EntregasPage = lazy(() => import('../pages/Inventario/EntregasPage'));
const ValoracionPage = lazy(() => import('../pages/Inventario/ValoracionPage'));
const PasosOperacionPage = lazy(() => import('../pages/Inventario/PasosOperacionPage'));
const ProductosPage = lazy(() => import('../pages/Inventario/ProductosPage'));
const AlmacenesPage = lazy(() => import('../pages/Inventario/AlmacenesPage'));
const InventarioMaestrosPage = lazy(() => import('../pages/Inventario/InventarioMaestrosPage'));

export function inventarioRoutes() {
  return (
    <>
      <Route path="/inventario" element={<InventarioDashboardPage />} />
      <Route path="/inventario/stock" element={<StockActualPage />} />
      <Route path="/inventario/kardex/:productoId" element={<KardexPage />} />
      <Route path="/inventario/ajustes" element={<AjusteInventarioPage />} />
      <Route path="/inventario/recepciones" element={<RecepcionesPage />} />
      <Route path="/inventario/entregas" element={<EntregasPage />} />
      <Route path="/inventario/valoracion" element={<ValoracionPage />} />
      <Route path="/inventario/pasos-operacion" element={<PasosOperacionPage />} />
      <Route path="/inventario/productos" element={<ProductosPage />} />
      <Route path="/inventario/almacenes" element={<AlmacenesPage />} />
      <Route path="/inventario/maestros" element={<InventarioMaestrosPage />} />
      <Route path="/inventario/variantes" element={<InventarioMaestrosPage />} />
      <Route path="/inventario/conversiones" element={<InventarioMaestrosPage />} />
      <Route path="/inventario/consignacion" element={<InventarioMaestrosPage />} />
    </>
  );
}
