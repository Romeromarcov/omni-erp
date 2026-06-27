import { lazy } from 'react';
import { Route } from 'react-router-dom';

const EmpleadosListPage = lazy(() => import('../pages/RRHH/EmpleadosListPage'));
const EmpleadoFormPage = lazy(() => import('../pages/RRHH/EmpleadoFormPage'));
const EmpleadoDetailPage = lazy(() => import('../pages/RRHH/EmpleadoDetailPage'));
const BeneficiosLicenciasPage = lazy(() => import('../pages/RRHH/BeneficiosLicenciasPage'));
const ProcesosNominaListPage = lazy(() => import('../pages/Nomina/ProcesosNominaListPage'));
const ProcesoNominaDetailPage = lazy(() => import('../pages/Nomina/ProcesoNominaDetailPage'));

/** Rutas del módulo RRHH + Nómina (workstream F). */
export function rrhhRoutes() {
  return (
    <>
      <Route path="/rrhh/empleados" element={<EmpleadosListPage />} />
      <Route path="/rrhh/empleados/nuevo" element={<EmpleadoFormPage />} />
      <Route path="/rrhh/empleados/:id" element={<EmpleadoDetailPage />} />
      <Route path="/rrhh/empleados/:id/editar" element={<EmpleadoFormPage />} />
      <Route path="/rrhh/beneficios" element={<BeneficiosLicenciasPage />} />
      <Route path="/rrhh/licencias" element={<BeneficiosLicenciasPage />} />
      <Route path="/nomina/procesos" element={<ProcesosNominaListPage />} />
      <Route path="/nomina/procesos/:id" element={<ProcesoNominaDetailPage />} />
    </>
  );
}
