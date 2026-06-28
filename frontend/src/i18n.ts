import i18n from 'i18next';
import { initReactI18next } from 'react-i18next';

// Traducciones legacy (facturas, notasVenta, pagos, pedidos, products…) y las
// completas por módulo (compras, tesoreria, manufactura, nomina, ventas…).
// Se fusionan para que TODAS las claves usadas por las páginas resuelvan; las
// completas (`./i18n/locales`) tienen prioridad sobre las legacy (`./locales`).
import esLegacy from './locales/es.json';
import esModulos from './i18n/locales/es.json';
import enModulos from './i18n/locales/en.json';

const es = { ...esLegacy, ...esModulos };
const en = { ...enModulos };

i18n
  .use(initReactI18next)
  .init({
    resources: {
      es: {
        translation: es,
      },
      en: {
        translation: en,
      },
    },
    lng: localStorage.getItem('lang') || 'es',
    fallbackLng: 'es',
    interpolation: {
      escapeValue: false, // React already does XSS escaping
    },
  });

export default i18n;
