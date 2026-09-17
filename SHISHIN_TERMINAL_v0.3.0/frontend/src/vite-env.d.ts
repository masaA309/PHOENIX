/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_SHISHIN_API_HOST?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
