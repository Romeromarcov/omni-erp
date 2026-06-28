import { lazy } from 'react';
import { Route } from 'react-router-dom';

const SolicitudesAprobacionPage = lazy(
  () => import('../pages/Aprobaciones/SolicitudesAprobacionPage'),
);
const ConfiguracionAprobacionesPage = lazy(
  () => import('../pages/Aprobaciones/ConfiguracionAprobacionesPage'),
);

export function aprobacionesRoutes() {
  return (
    <>
      <Route path="/aprobaciones/solicitudes" element={<SolicitudesAprobacionPage />} />
      <Route path="/aprobaciones/configuracion" element={<ConfiguracionAprobacionesPage />} />
    </>
  );
}
