const { defineConfig } = require('@playwright/test');
const path = require('path');

module.exports = defineConfig({
  testDir: './tests',
  timeout: 30000,
  expect: { timeout: 5000 },
  fullyParallel: true,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: 'http://localhost:8765',
    headless: true,
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: 'npx serve . -l 8765 --no-clipboard',
    port: 8765,
    reuseExistingServer: true,
  },
});
