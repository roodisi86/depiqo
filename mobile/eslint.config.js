// https://docs.expo.dev/guides/using-eslint/
const { defineConfig } = require('eslint/config');
const expoConfig = require('eslint-config-expo/flat');

module.exports = defineConfig([
  expoConfig,
  {
    ignores: ['dist/*', 'node_modules/*', 'scripts/*', 'coverage/*', '.expo/*'],
  },
  {
    rules: {
      // No logging of tokens or personal data: console is off everywhere except src/lib/log.ts.
      'no-console': 'error',
    },
  },
  {
    files: ['src/lib/log.ts'],
    rules: { 'no-console': 'off' },
  },
]);
