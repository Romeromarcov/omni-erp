/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Versión del bundle; invalida el caché persistido de TanStack al cambiar (CTF-008). */
  readonly VITE_APP_VERSION?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
