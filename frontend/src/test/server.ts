/**
 * Servidor MSW para tests de Vitest (entorno Node/jsdom).
 *
 * Se arranca/limpia en `src/test-setup.ts`. Los tests pueden sobreescribir
 * handlers por caso con `server.use(...)` y se resetean tras cada test.
 */
import { setupServer } from 'msw/node';
import { handlers } from './handlers';

export const server = setupServer(...handlers);
