import js from '@eslint/js'
import globals from 'globals'
import reactHooks from 'eslint-plugin-react-hooks'
import reactRefresh from 'eslint-plugin-react-refresh'
import security from 'eslint-plugin-security'
import tseslint from 'typescript-eslint'
import { globalIgnores } from 'eslint/config'

export default tseslint.config([
  // `src/api/schema.d.ts` es código generado (openapi-typescript); no se lintea.
  globalIgnores(['dist', 'coverage', 'src/api/schema.d.ts']),
  // CTF-006: eslint-plugin-security en TODO el código linteado (src, e2e,
  // scripts, electron). Sin `files` aplica globalmente. Las reglas recommended
  // vienen como "warn" y `npm run lint` no usa --max-warnings, así que se
  // elevan a "error" para que el job de lint (BLOQUEANTE en CI) falle ante
  // cualquier hallazgo nuevo. Falsos positivos: suprimir SOLO en la línea con
  // `eslint-disable-next-line security/<regla> -- justificación`.
  {
    ...security.configs.recommended,
    rules: Object.fromEntries(
      Object.keys(security.configs.recommended.rules).map((regla) => [regla, 'error']),
    ),
  },
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      js.configs.recommended,
      tseslint.configs.recommended,
      reactHooks.configs['recommended-latest'],
      reactRefresh.configs.vite,
    ],
    rules: {
      '@typescript-eslint/no-unused-vars': ['error', {
        argsIgnorePattern: '^_',
        varsIgnorePattern: '^_',
        caughtErrorsIgnorePattern: '^_',
      }],
    },
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
  },
  // E2E (Playwright) y config: corren en Node, no en el navegador.
  {
    files: ['e2e/**/*.{ts,tsx}', 'playwright.config.ts'],
    languageOptions: {
      globals: { ...globals.node },
    },
  },
  // Scripts de build/tooling en ESM de Node.
  {
    files: ['scripts/**/*.{mjs,js}'],
    extends: [js.configs.recommended],
    languageOptions: {
      ecmaVersion: 2022,
      sourceType: 'module',
      globals: { ...globals.node },
    },
  },
])
