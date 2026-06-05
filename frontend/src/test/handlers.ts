/**
 * Handlers MSW para los endpoints REALES del backend.
 *
 * La base coincide con la que resuelve `services/api.ts` en entorno de test:
 * sin `VITE_API_URL`, `API_URL` cae a `http://localhost:8000/api`. Los paths
 * provienen de los servicios reales (`src/services/`) y de las query keys
 * (`src/lib/queryKeys.ts`); no se inventan rutas.
 */
import { http, HttpResponse } from 'msw';

export const API_BASE = 'http://localhost:8000/api';

/** Construye una URL absoluta sobre la base de la API real. */
export const apiUrl = (path: string): string => `${API_BASE}${path}`;

export const handlers = [
  // services/empresas.ts → get('/core/empresas/')
  http.get(apiUrl('/core/empresas/'), () =>
    HttpResponse.json([
      {
        id_empresa: 'emp-1',
        nombre_legal: 'Distribuidora Demo C.A.',
        nombre_comercial: 'Demo',
        identificador_fiscal: 'J-12345678-9',
        email_contacto: 'demo@example.com',
        activo: true,
        fecha_registro: '2026-01-01',
      },
    ]),
  ),

  // hooks/useCxC.ts → get('/cobranza/cartera/dashboard/')
  http.get(apiUrl('/cobranza/cartera/dashboard/'), () =>
    HttpResponse.json({ total_pendiente: '1500.00', buckets: { '0-30': '1500.00' } }),
  ),

  // hooks/useCxC.ts → get('/cobranza/acuerdos/')
  http.get(apiUrl('/cobranza/acuerdos/'), () => HttpResponse.json({ results: [] })),

  // services/auth.ts → POST /auth/login/ (smoke de login en componente)
  http.post(apiUrl('/auth/login/'), () =>
    HttpResponse.json({ access: 'fake-access-token' }),
  ),

  // components/NotificationBell.tsx → GET mis-notificaciones
  http.get(apiUrl('/notificaciones/notificaciones/mis-notificaciones/'), () =>
    HttpResponse.json([]),
  ),
];
