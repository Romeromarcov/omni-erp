import { lazy } from 'react';
import { Route } from 'react-router-dom';

const CuentasBancariasEmpresaPage = lazy(
  () => import('../pages/BancaElectronica/CuentasBancariasEmpresaPage'),
);

export function bancaElectronicaRoutes() {
  return (
    <>
      <Route path="/banca-electronica" element={<CuentasBancariasEmpresaPage />} />
    </>
  );
}
