# React + TypeScript + Vite

This template provides a minimal setup to get React working in Vite with HMR and some ESLint rules.

Currently, two official plugins are available:

- [@vitejs/plugin-react](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react) uses [Babel](https://babeljs.io/) for Fast Refresh
- [@vitejs/plugin-react-swc](https://github.com/vitejs/vite-plugin-react/blob/main/packages/plugin-react-swc) uses [SWC](https://swc.rs/) for Fast Refresh

## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default tseslint.config([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],

# Frontend ERP - React Native Multiplataforma

Este proyecto está basado en React + Vite + TypeScript, optimizado para web, mobile y desktop (usando react-native-web y electron).

## Estructura recomendada
- `src/components`: Componentes reutilizables
- `src/pages`: Vistas principales (Dashboard, etc.)
- `src/services`: Conexión a la API backend (Django)
- `src/hooks`: Hooks personalizados
- `src/types`: Tipos y modelos
- `src/assets`: Imágenes, íconos, estilos
- `src/utils`: Utilidades generales

## Diseño
El diseño base replica el dashboard adjunto, con módulos, acciones rápidas y métricas principales.

## Conexión Backend
La comunicación se realiza vía API REST, respetando los modelos definidos en Django.

## Multiplataforma
- Web: Vite + React
- Mobile/Desktop: Integración con react-native-web y electron

## Instalación
```bash
npm install
npm run dev
```

## Personalización
Reemplaza los assets y ajusta los endpoints según tu backend.
  {
