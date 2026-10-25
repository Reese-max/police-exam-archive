const { defineConfig } = require('@playwright/test');
const port = Number(process.env.PLAYWRIGHT_PORT || 8765);

module.exports = defineConfig({
  testDir: './tests',
  timeout: 30000,
  expect: { timeout: 5000 },
  fullyParallel: true,
  retries: 0,
  reporter: 'list',
  use: {
    baseURL: `http://localhost:${port}`,
    headless: true,
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `python -X utf8 ../scripts/build_search_index.py && npx serve . -l ${port} --no-clipboard`,
    port,
    reuseExistingServer: false,
    timeout: 120000,
  },
});
