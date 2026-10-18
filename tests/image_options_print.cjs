/* Native-print regression. Requires the site's declared Playwright dependency and a browser. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
const { createRequire } = require('node:module');
const root = path.resolve(__dirname, '..');
const site = path.join(root, '考古題網站');
const { chromium } = createRequire(path.join(site, 'package.json'))('playwright');

(async () => {
  const generated = execFileSync('python', ['-X', 'utf8', '-c',
    'import runpy; print(runpy.run_path("archive/misc/generate_html.py")["generate_shared_css"]())'
  ], { cwd: root, encoding: 'utf8' });
  const styles = [['published', fs.readFileSync(path.join(site, 'css/style.css'), 'utf8')], ['generated', generated]];
  const locator = 'archive/canonical/109/subject/Exam.pdf';
  const hash = '0123456789abcdef'.repeat(4);
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'pr71-print-'));
  const browser = await chromium.launch({ channel: process.platform === 'win32' ? 'msedge' : undefined });
  try {
    const page = await browser.newPage();
    for (const [name, css] of styles) {
      await page.setContent(`<style>${css}</style><div class="q-block" data-source-pdf="${locator}" data-source-page="2" data-source-sha256="${hash}">Question</div>`);
      const pdf = path.join(out, name + '.pdf');
      await page.pdf({ path: pdf });
      const text = execFileSync('python', ['-X', 'utf8', '-c',
        'import logging, pdfplumber, sys; logging.getLogger("pdfminer").setLevel(logging.ERROR); pdf = pdfplumber.open(sys.argv[1]); print("".join(page.extract_text() or "" for page in pdf.pages)); pdf.close()', pdf
      ], { encoding: 'utf8' }).replace(/\s/g, '');
      assert.ok(text.includes(locator), `${name} native PDF lost the source locator`);
      assert.ok(text.includes(hash), `${name} native PDF lost the source hash`);
    }
    console.log('2 native-print provenance cases passed; PDFs: ' + out);
  } finally {
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
