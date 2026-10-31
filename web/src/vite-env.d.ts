/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_BOT_USERNAME?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}

// Подставляются vite.config.ts при сборке.
declare const __APP_COMMIT__: string;
declare const __APP_COMMIT_DATE__: string;
