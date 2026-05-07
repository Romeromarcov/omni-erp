import { Route } from 'react-router-dom';
import CuentaBancariaListPage from '../pages/Finanzas/CuentasBancarias/CuentaBancariaListPage';
import CuentaBancariaCreatePage from '../pages/Finanzas/CuentasBancarias/CuentaBancariaCreatePage';
import CuentaBancariaDetailPage from '../pages/Finanzas/CuentasBancarias/CuentaBancariaDetailPage';
import CuentaBancariaMovimientosListPage from '../pages/Finanzas/CuentasBancarias/CuentaBancariaMovimientosListPage';
import TasaCambioListPage from '../pages/Finanzas/TasasCambio/TasaCambioListPage';
import TasaCambioCreatePage from '../pages/Finanzas/TasasCambio/TasaCambioCreatePage';
import TasaCambioDetailPage from '../pages/Finanzas/TasasCambio/TasaCambioDetailPage';
import MetodoPagoListPage from '../pages/Finanzas/MetodoPago/MetodoPagoListPage';
import MetodoPagoDetailPage from '../pages/Finanzas/MetodoPago/MetodoPagoDetailPage';
import MetodoPagoCreatePage from '../pages/Finanzas/MetodoPago/MetodoPagoCreatePage';
import MonedaListPage from '../pages/Finanzas/Monedas/MonedaListPage';
import MonedaDetailPage from '../pages/Finanzas/Monedas/MonedaDetailPage';
import MonedaFormPage from '../pages/Finanzas/Monedas/MonedaFormPage';
import TransaccionFinancieraListPage from '../pages/Finanzas/TransaccionFinanciera/TransaccionFinancieraListPage';
import TransaccionFinancieraDetailPage from '../pages/Finanzas/TransaccionFinanciera/TransaccionFinancieraDetailPage';
import TransaccionFinancieraFormPage from '../pages/Finanzas/TransaccionFinanciera/TransaccionFinancieraFormPage';
import CajaListPage from '../pages/Finanzas/Cajas/CajaListPage';
import CajaDetailPage from '../pages/Finanzas/Cajas/CajaDetailPage';
import CajaMovimientosListPage from '../pages/Finanzas/Cajas/CajaMovimientosListPage';
import CajaCreatePage from '../pages/Finanzas/Cajas/CajaCreatePage';
import PlantillasMaestroListPage from '../pages/Finanzas/Cajas/PlantillasMaestroListPage';
import PlantillaMaestroFormPage from '../pages/Finanzas/Cajas/PlantillaMaestroFormPage';
import OverridesMetodosPagoPage from '../pages/Finanzas/Cajas/OverridesMetodosPagoPage';
import CajasFisicasListPage from '../pages/Finanzas/Cajas/CajasFisicasListPage';
import CajaFisicaDetailPage from '../pages/Finanzas/Cajas/CajaFisicaDetailPage';
import CajaFisicaFormPage from '../pages/Finanzas/Cajas/CajaFisicaFormPage';

export function finanzasRoutes() {
  return (
    <>
      <Route path="/finanzas/monedas" element={<MonedaListPage />} />
      <Route path="/finanzas/monedas/new" element={<MonedaFormPage />} />
      <Route path="/finanzas/monedas/:id_moneda" element={<MonedaDetailPage />} />

      <Route path="/empresas/:id_empresa/metodos-pago" element={<MetodoPagoListPage />} />
      <Route path="/empresas/:id_empresa/metodos-pago/new" element={<MetodoPagoCreatePage />} />
      <Route path="/metodos-pago/:id_metodo_pago" element={<MetodoPagoDetailPage />} />

      <Route path="/empresas/:id_empresa/tasas-cambio" element={<TasaCambioListPage />} />
      <Route path="/empresas/:id_empresa/tasas-cambio/new" element={<TasaCambioCreatePage />} />
      <Route path="/tasas-cambio/:id_tasa_cambio" element={<TasaCambioDetailPage />} />

      <Route path="/empresas/:id_empresa/cajas" element={<CajaListPage />} />
      <Route path="/empresas/:id_empresa/cajas/new" element={<CajaCreatePage />} />
      <Route path="/cajas/:id_caja" element={<CajaDetailPage />} />
      <Route path="/cajas/:id_caja/movimientos-caja-banco" element={<CajaMovimientosListPage />} />

      <Route path="/finanzas/plantillas-maestro" element={<PlantillasMaestroListPage />} />
      <Route path="/finanzas/plantillas-maestro/crear" element={<PlantillaMaestroFormPage />} />
      <Route path="/finanzas/plantillas-maestro/:id" element={<PlantillaMaestroFormPage />} />

      <Route path="/finanzas/overrides-metodos-pago" element={<OverridesMetodosPagoPage />} />

      <Route path="/finanzas/cajas-fisicas" element={<CajasFisicasListPage />} />
      <Route path="/finanzas/cajas-fisicas/:id" element={<CajaFisicaDetailPage />} />
      <Route path="/finanzas/cajas-fisicas/crear" element={<CajaFisicaFormPage />} />
      <Route path="/finanzas/cajas-fisicas/:id/:action" element={<CajaFisicaFormPage />} />

      <Route path="/empresas/:id_empresa/cuentas-bancarias" element={<CuentaBancariaListPage />} />
      <Route path="/empresas/:id_empresa/cuentas-bancarias/new" element={<CuentaBancariaCreatePage />} />
      <Route path="/cuentas-bancarias/:id_cuenta" element={<CuentaBancariaDetailPage />} />
      <Route path="/cuentas-bancarias/:id_cuenta/movimientos" element={<CuentaBancariaMovimientosListPage />} />

      <Route path="/empresas/:id_empresa/transacciones-financieras" element={<TransaccionFinancieraListPage />} />
      <Route path="/empresas/:id_empresa/transacciones-financieras/new" element={<TransaccionFinancieraFormPage />} />
      <Route path="/transacciones-financieras/:id_transaccion" element={<TransaccionFinancieraDetailPage />} />
    </>
  );
}
