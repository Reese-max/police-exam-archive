const { test, expect } = require('@playwright/test');
const { mkdirSync, writeFileSync, existsSync } = require('node:fs');
const { spawnSync } = require('node:child_process');
const net = require('node:net');
const path = require('node:path');

test('a foreign listener during index construction cannot release the browser suite', async ({}, info) => {
  test.setTimeout(30000);
  const reservation = net.createServer();
  await new Promise(resolve => reservation.listen(0, '127.0.0.1', resolve));
  const port = reservation.address().port;
  await new Promise(resolve => reservation.close(resolve));

  const dir = info.outputPath('startup-race');
  mkdirSync(dir, { recursive: true });
  const ready = path.join(dir, 'foreign-ready');
  const ran = path.join(dir, 'tests-started');
  const builder = path.join(dir, 'builder.js');
  writeFileSync(builder, `
    const fs = require('node:fs');
    require('node:http').createServer((req, res) => res.end('other worktree'))
      .listen(${port}, '127.0.0.1', () => fs.writeFileSync(${JSON.stringify(ready)}, 'ready'));
    // Keep the simulated index build pending while a foreign server owns the port.
  `);
  writeFileSync(path.join(dir, 'probe.test.js'), `
    const { test } = require(${JSON.stringify(require.resolve('@playwright/test'))});
    test('must never start against the foreign listener', () => {
      require('node:fs').writeFileSync(${JSON.stringify(ran)}, 'started');
    });
  `);
  const config = path.join(dir, 'playwright.config.js');
  writeFileSync(config, `
    const config = require(${JSON.stringify(require.resolve('../playwright.config'))});
    module.exports = { ...config, testDir: __dirname, testMatch: 'probe.test.js',
      outputDir: ${JSON.stringify(path.join(dir, 'results'))}, reporter: 'line',
      webServer: { ...config.webServer, cwd: ${JSON.stringify(path.resolve(__dirname, '..'))},
        command: ${JSON.stringify(`"${process.execPath}" "${builder}"`)} + ' && ' +
          config.webServer.command.split(' && ').slice(1).join(' && '), timeout: 5000 } };
  `);
  const result = spawnSync(process.execPath, [require.resolve('@playwright/test/cli'),
    'test', '--config', config, '--workers=1'], {
    env: { ...process.env, PLAYWRIGHT_PORT: String(port) },
    encoding: 'utf8', timeout: 20000,
  });
  expect(result.error).toBeUndefined();
  expect(existsSync(ready), result.stdout + result.stderr).toBe(true);
  expect(existsSync(ran), 'tests ran before the owned server started').toBe(false);
  expect(result.status, result.stdout + result.stderr).not.toBe(0);
});
