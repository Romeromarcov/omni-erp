import { lazy } from 'react';
import { Route } from 'react-router-dom';

const DocumentosPage = lazy(() => import('../pages/GestionDocumental/DocumentosPage'));

export function gestionDocumentalRoutes() {
  return (
    <>
      <Route path="/gestion-documental/documentos" element={<DocumentosPage />} />
    </>
  );
}
