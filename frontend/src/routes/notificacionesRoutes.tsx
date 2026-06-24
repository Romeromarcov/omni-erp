import { lazy } from 'react';
import { Route } from 'react-router-dom';

const NotificacionesPage = lazy(() => import('../pages/Notificaciones/NotificacionesPage'));

export function notificacionesRoutes() {
  return <Route path="/notificaciones" element={<NotificacionesPage />} />;
}
