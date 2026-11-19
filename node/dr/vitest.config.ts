// Integration tests (`*.integration.test.ts`) run only with LA_INTEGRATION=1 (`npm run test:integration`).
import { configDefaults, defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    exclude: [...configDefaults.exclude, ...(process.env.LA_INTEGRATION === '1' ? [] : ['**/*.integration.test.ts'])],
  },
});
