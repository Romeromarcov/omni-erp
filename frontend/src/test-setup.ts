import '@testing-library/jest-dom';
import { afterAll, afterEach, beforeAll } from 'vitest';
import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';
import es from './i18n/locales/es.json';
import en from './i18n/locales/en.json';
import { server } from './test/server';

// ── MSW (TEST-6) ──────────────────────────────────────────────────────────────
// Servidor de mocks de red compartido por toda la suite. `onUnhandledRequest:
// 'bypass'` evita romper los tests existentes que ya mockean `services/api`
// (esos nunca llegan a la red); los tests que usan MSW sí golpean handlers.
beforeAll(() => server.listen({ onUnhandledRequest: 'bypass' }));
afterEach(() => server.resetHandlers());
afterAll(() => server.close());

// Initialize i18n for all tests — use real translations so t('key') returns actual strings
if (!i18n.isInitialized) {
  i18n.use(initReactI18next).init({
    resources: {
      es: { translation: es },
      en: { translation: en },
    },
    lng: 'es',
    fallbackLng: 'es',
    interpolation: { escapeValue: false },
  });
}
