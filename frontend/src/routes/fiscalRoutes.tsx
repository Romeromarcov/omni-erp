import { Route } from 'react-router-dom';
import ConfiguracionFiscalPage from '../pages/Fiscal/ConfiguracionFiscalPage';
import LibroVentasPage from '../pages/Fiscal/LibroVentasPage';
import LibroComprasPage from '../pages/Fiscal/LibroComprasPage';

export function fiscalRoutes() {
  return (
    <>
      <Route path="/configuracion/fiscal" element={<ConfiguracionFiscalPage />} />
      <Route path="/fiscal/libro-ventas" element={<LibroVentasPage />} />
      <Route path="/fiscal/libro-compras" element={<LibroComprasPage />} />
    </>
  );
}
