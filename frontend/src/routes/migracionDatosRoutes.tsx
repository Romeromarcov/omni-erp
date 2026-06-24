import { lazy } from 'react';
import { Route } from 'react-router-dom';

const MigracionDatosPage = lazy(() => import('../pages/MigracionDatos/MigracionDatosPage'));

export function migracionDatosRoutes() {
  return (
    <>
      <Route path="/migracion-datos" element={<MigracionDatosPage />} />
    </>
  );
}
