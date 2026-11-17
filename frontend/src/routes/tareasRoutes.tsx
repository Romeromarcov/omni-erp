import { lazy } from 'react';
import { Route } from 'react-router-dom';

const TareasPage = lazy(() => import('../pages/Tareas/TareasPage'));

export function tareasRoutes() {
  return (
    <>
      <Route path="/tareas" element={<TareasPage />} />
      <Route path="/tareas/:tareaId" element={<TareasPage />} />
    </>
  );
}
