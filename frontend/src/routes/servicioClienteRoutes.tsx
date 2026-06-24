import { lazy } from 'react';
import { Route } from 'react-router-dom';

const TicketsPage = lazy(() => import('../pages/ServicioCliente/TicketsPage'));
const CategoriasTicketPage = lazy(() => import('../pages/ServicioCliente/CategoriasTicketPage'));
const BaseConocimientoPage = lazy(() => import('../pages/ServicioCliente/BaseConocimientoPage'));
const FeedbackPage = lazy(() => import('../pages/ServicioCliente/FeedbackPage'));

export function servicioClienteRoutes() {
  return (
    <>
      <Route path="/servicio-cliente/tickets" element={<TicketsPage />} />
      <Route path="/servicio-cliente/categorias" element={<CategoriasTicketPage />} />
      <Route path="/servicio-cliente/base-conocimiento" element={<BaseConocimientoPage />} />
      <Route path="/servicio-cliente/feedback" element={<FeedbackPage />} />
    </>
  );
}
