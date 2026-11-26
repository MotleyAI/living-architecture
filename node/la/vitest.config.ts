// `type-rename-move/<module>` resolves to trmv's sources, as la's tsconfig maps it, so tests need no trmv build.
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

const TRMV_SRC = fileURLToPath(new URL('../trmv/src', import.meta.url));

export default defineConfig({
  resolve: { alias: [{ find: /^type-rename-move\/(.*)$/, replacement: `${TRMV_SRC}/$1/index.ts` }] },
});
