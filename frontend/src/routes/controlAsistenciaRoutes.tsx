import { lazy } from 'react';
import { Route } from 'react-router-dom';

const ControlAsistenciaPage = lazy(() => import('../pages/ControlAsistencia/ControlAsistenciaPage'));

export function controlAsistenciaRoutes() {
  return (
    <>
      <Route path="/control-asistencia" element={<ControlAsistenciaPage />} />
    </>
  );
}
