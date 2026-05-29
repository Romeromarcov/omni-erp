import { Route } from 'react-router-dom';
import DashboardCxCPage from '../pages/CxC/DashboardCxCPage';
import CobranzaPage from '../pages/CxC/CobranzaPage';
import AcuerdosPage from '../pages/CxC/AcuerdosPage';
import AgenteCobranzaPage from '../pages/CxC/AgenteCobranzaPage';

export function cxcRoutes() {
  return (
    <>
      <Route path="/cobranza/dashboard" element={<DashboardCxCPage />} />
      <Route path="/cobranza/gestiones" element={<CobranzaPage />} />
      <Route path="/cobranza/acuerdos" element={<AcuerdosPage />} />
      <Route path="/cobranza/agente" element={<AgenteCobranzaPage />} />
    </>
  );
}
