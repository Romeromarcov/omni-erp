import { lazy } from 'react';
import { Route } from 'react-router-dom';

const PersonalizacionPage = lazy(() => import('../pages/Personalizacion/PersonalizacionPage'));

export function personalizacionRoutes() {
  return (
    <>
      <Route path="/personalizacion" element={<PersonalizacionPage />} />
    </>
  );
}
