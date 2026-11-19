// `deterministic-refactor/<module>` resolves to dr's sources, as la's tsconfig maps it, so tests need no dr build.
import { fileURLToPath } from 'node:url';
import { defineConfig } from 'vitest/config';

const DR_SRC = fileURLToPath(new URL('../dr/src', import.meta.url));

export default defineConfig({
  resolve: { alias: [{ find: /^deterministic-refactor\/(.*)$/, replacement: `${DR_SRC}/$1/index.ts` }] },
});
