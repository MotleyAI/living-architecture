import js from '@eslint/js';
import globals from 'globals';
import tseslint from 'typescript-eslint';

export default tseslint.config(
  { ignores: ['dist/', 'node_modules/', 'src/contract/data/'] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  { files: ['scripts/**/*.mjs', 'eslint.config.mjs'], languageOptions: { globals: globals.node } },
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'off',
    },
  },
);
