// Integration tests (`*.integration.test.ts`) run only with LA_INTEGRATION=1 (`npm run test:integration`).
// `deterministic-refactor/<module>` resolves to dr's sources, as la's tsconfig maps it, so tests need no dr build.
import { fileURLToPath } from 'node:url';
import { configDefaults, defineConfig } from 'vitest/config';

const DR_SRC = fileURLToPath(new URL('../dr/src', import.meta.url));

export default defineConfig({
  resolve: { alias: [{ find: /^deterministic-refactor\/(.*)$/, replacement: `${DR_SRC}/$1/index.ts` }] },
  test: {
    exclude: [...configDefaults.exclude, ...(process.env.LA_INTEGRATION === '1' ? [] : ['**/*.integration.test.ts'])],
  },
});
