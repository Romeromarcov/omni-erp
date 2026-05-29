 
import { lazy } from 'react';
import { Route } from 'react-router-dom';

const CuentaBancariaListPage = lazy(() => import('../pages/Finanzas/CuentasBancarias/CuentaBancariaListPage'));
const CuentaBancariaCreatePage = lazy(() => import('../pages/Finanzas/CuentasBancarias/CuentaBancariaCreatePage'));
const CuentaBancariaDetailPage = lazy(() => import('../pages/Finanzas/CuentasBancarias/CuentaBancariaDetailPage'));
const CuentaBancariaMovimientosListPage = lazy(() => import('../pages/Finanzas/CuentasBancarias/CuentaBancariaMovimientosListPage'));
const TasaCambioListPage = lazy(() => import('../pages/Finanzas/TasasCambio/TasaCambioListPage'));
const TasaCambioCreatePage = lazy(() => import('../pages/Finanzas/TasasCambio/TasaCambioCreatePage'));
const TasaCambioDetailPage = lazy(() => import('../pages/Finanzas/TasasCambio/TasaCambioDetailPage'));
const MetodoPagoListPage = lazy(() => import('../pages/Finanzas/MetodoPago/MetodoPagoListPage'));
const MetodoPagoDetailPage = lazy(() => import('../pages/Finanzas/MetodoPago/MetodoPagoDetailPage'));
const MetodoPagoCreatePage = lazy(() => import('../pages/Finanzas/MetodoPago/MetodoPagoCreatePage'));
const MonedaListPage = lazy(() => import('../pages/Finanzas/Monedas/MonedaListPage'));
const MonedaDetailPage = lazy(() => import('../pages/Finanzas/Monedas/MonedaDetailPage'));
const MonedaFormPage = lazy(() => import('../pages/Finanzas/Monedas/MonedaFormPage'));
const TransaccionFinancieraListPage = lazy(() => import('../pages/Finanzas/TransaccionFinanciera/TransaccionFinancieraListPage'));
const TransaccionFinancieraDetailPage = lazy(() => import('../pages/Finanzas/TransaccionFinanciera/TransaccionFinancieraDetailPage'));
const TransaccionFinancieraFormPage = lazy(() => import('../pages/Finanzas/TransaccionFinanciera/TransaccionFinancieraFormPage'));
const CajaListPage = lazy(() => import('../pages/Finanzas/Cajas/CajaListPage'));
const CajaDetailPage = lazy(() => import('../pages/Finanzas/Cajas/CajaDetailPage'));
const CajaMovimientosListPage = lazy(() => import('../pages/Finanzas/Cajas/CajaMovimientosListPage'));
const CajaCreatePage = lazy(() => import('../pages/Finanzas/Cajas/CajaCreatePage'));
const PlantillasMaestroListPage = lazy(() => import('../pages/Finanzas/Cajas/PlantillasMaestroListPage'));
const PlantillaMaestroFormPage = lazy(() => import('../pages/Finanzas/Cajas/PlantillaMaestroFormPage'));
const OverridesMetodosPagoPage = lazy(() => import('../pages/Finanzas/Cajas/OverridesMetodosPagoPage'));
const CajasFisicasListPage = lazy(() => import('../pages/Finanzas/Cajas/CajasFisicasListPage'));
const CajaFisicaDetailPage = lazy(() => import('../pages/Finanzas/Cajas/CajaFisicaDetailPage'));
const CajaFisicaFormPage = lazy(() => import('../pages/Finanzas/Cajas/CajaFisicaFormPage'));

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
