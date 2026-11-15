import { test as base } from '@playwright/test';

export * from '@playwright/test';

/**
 * `test` de Playwright para los E2E: cada carga de documento arranca con la caché de datos
 * persistida de la app VACÍA.
 *
 * La app persiste el caché de TanStack Query en IndexedDB (`omni-erp-cache`, ver
 * `src/lib/idbPersister.ts`; offline Nivel 1, ADR-001) y lo rehidrata al cargar. Con
 * `staleTime` de 30 s, una consulta rehidratada se considera fresca y NO se vuelve a pedir al
 * backend. Los specs mutan datos por API y luego recargan o navegan (`page.reload()`,
 * `page.goto()`): si el caché ya se había persistido (el guardado tiene 1 s de retardo), la UI
 * mostraba el estado anterior (p. ej. PENDIENTE en vez de APROBADO). Que el test pasara o no
 * dependía de la velocidad de la máquina, por eso fallaba de forma intermitente en el CI.
 *
 * Los E2E prueban la aplicación contra el backend real, no el caché offline. El script de
 * inicio se ejecuta antes que el código de la página en cada navegación, así que la petición
 * de borrado se encola antes de que la app abra la base.
 */
export const test = base.extend({
  // El segundo parámetro se llama `entregar` y no `use` (nombre de Playwright) para que la regla
  // react-hooks/rules-of-hooks no lo confunda con un hook de React.
  context: async ({ context }, entregar) => {
    await context.addInitScript(() => {
      try {
        indexedDB.deleteDatabase('omni-erp-cache');
      } catch {
        // Sin IndexedDB no hay caché persistido que vaciar.
      }
    });
    await entregar(context);
  },
});
