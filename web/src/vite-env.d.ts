/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_RUST_API_ORIGIN?: string;
  readonly VITE_PYTHON_API_ORIGIN?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
