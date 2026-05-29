 
import { lazy } from 'react';
import { Route } from 'react-router-dom';

const ConfiguracionFiscalPage = lazy(() => import('../pages/Fiscal/ConfiguracionFiscalPage'));
const LibroVentasPage = lazy(() => import('../pages/Fiscal/LibroVentasPage'));
const LibroComprasPage = lazy(() => import('../pages/Fiscal/LibroComprasPage'));

export function fiscalRoutes() {
  return (
    <>
      <Route path="/configuracion/fiscal" element={<ConfiguracionFiscalPage />} />
      <Route path="/fiscal/libro-ventas" element={<LibroVentasPage />} />
      <Route path="/fiscal/libro-compras" element={<LibroComprasPage />} />
    </>
  );
}
