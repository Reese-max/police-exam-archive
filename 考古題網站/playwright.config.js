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
    baseURL: `http://127.0.0.1:${port}`,
    headless: true,
    screenshot: 'only-on-failure',
  },
  webServer: {
    command: `python -X utf8 ../scripts/build_search_index.py && python -u -m http.server ${port} --bind 127.0.0.1`,
    // Port polling can accept another worktree while the index is still building.
    wait: { stdout: new RegExp(`Serving HTTP on 127\\.0\\.0\\.1 port ${port} `) },
    reuseExistingServer: false,
    timeout: 120000,
  },
});
