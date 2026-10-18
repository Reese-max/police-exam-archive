/* Executable consumer regressions, invoked by test_image_options.py; no browser or npm install. */
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const input = JSON.parse(fs.readFileSync(0, 'utf8'));
const site = path.join(__dirname, '..', '考古題網站');

async function main() {
  if (input.mode === 'source-click') {
    const fn = input.js.match(/function bindOptionClicks\(\) \{[\s\S]*?\n\}/);
    assert.ok(fn, 'missing real option click handler');
    let handler, selections = 0;
    const opt = { addEventListener: (_, fn) => { handler = fn; }, closest: () => { selections++; return null; } };
    vm.runInNewContext(fn[0] + '; bindOptionClicks();', {
      practiceMode: true, document: { querySelectorAll: () => [opt] }
    });
    handler({ target: { closest: () => ({ tagName: 'A' }) } });
    assert.equal(selections, 0, 'source link submitted an answer');
    handler({ target: { closest: () => null } });
    assert.equal(selections, 1, 'ordinary option click must still select');
  } else if (input.mode === 'search') {
    const window = {};
    vm.runInNewContext(fs.readFileSync(path.join(site, 'js/search-engine.js'), 'utf8'), {
      window, fetch: async () => ({ ok: true, json: async () => input.index }),
      MiniSearch: class { addAll() {} }
    });
    await window.SearchEngine.loadIndex('');
    for (const expected of input.expected) {
      const results = window.SearchEngine.search('', { cat: expected.category, yr: expected.year, type: 'choice' }, 99999);
      assert.ok(results.some(q => q.optImages?.options.A.src === expected.src),
        `normal category filter lost image question: ${expected.category}/${expected.year}`);
    }
  } else if (input.mode === 'pdf') {
    for (const q of input.questions) {
      for (const includeAnswers of [false, true]) {
        const events = [];
        const images = Object.values(q.option_images);
        const element = (textContent = '', selectors = {}, lists = {}) => ({
          textContent, querySelector: key => selectors[key] || null,
          querySelectorAll: key => lists[key] || [], getAttribute: () => null
        });
        const options = images.map((image, i) => element('', {
          '.opt-label': element('(' + 'ABCD'[i] + ')'),
          '.opt-image img': { src: image.public_src, alt: image.alt }
        }));
        const block = element('', {
          '.mc-question': element('', { '.q-number': element(String(q.number)), '.q-text': element(q.stem) }),
          '.q-answer': element('ANSWER ' + q.answer)
        }, { '.mc-opt': options });
        block.className = 'q-block';
        block.getAttribute = key => ({ 'data-source-pdf': q.source_locator.pdf,
          'data-source-page': String(q.source_locator.page), 'data-source-sha256': q.source_locator.pdf_sha256 }[key]);
        const card = element('', {
          '.subject-header h3': element('subject'), '.subject-body': { querySelector: () => null, children: [block] }
        });
        const section = element('', { '.year-heading': element('109年') }, { '.subject-card': [card] });
        const document = element('', { '.page-title': element('Archive') }, { '#yearView .year-section': [section] });
        const font = { widthOfTextAtSize: text => text.length * 2 };
        const page = {
          drawText: text => events.push({ text }), drawImage: image => events.push({ image }),
          drawLine() {}, drawRectangle() {}
        };
        const doc = {
          registerFontkit() {}, embedFont: async () => font, addPage: () => page,
          embedPng: async bytes => ({ scale: () => ({ width: 20, height: 20 }), label: bytes[2] }),
          save: async () => new Uint8Array([37, 80, 68, 70])
        };
        const window = { PDFLib: { PDFDocument: { create: async () => doc }, rgb: (...v) => v } };
        vm.runInNewContext(fs.readFileSync(path.join(site, 'js/pdf-export.js'), 'utf8'), {
          window, document, setTimeout,
          fetch: async src => ({ ok: true, arrayBuffer: async () =>
            Uint8Array.from([0x89, 0x50, images.findIndex(image => image.public_src === src)]).buffer })
        });
        await window.PdfExport.generatePdf({ years: ['109'], subjects: ['subject'] }, includeAnswers);
        const text = events.map(e => e.text || '').join('');
        assert.ok(text.includes(q.source_locator.pdf), 'PDF lost the full source locator');
        assert.ok(text.includes(q.source_locator.pdf_sha256), 'PDF lost the source hash');
        assert.equal(text.includes('ANSWER ' + q.answer), includeAnswers, 'answer visibility changed');
        assert.deepEqual(events.filter(e => e.image).map(e => e.image.label), [0, 1, 2, 3], 'image order changed');
        for (const label of 'ABCD') assert.ok(text.includes(`(${label}) 圖片選項`));
        if (includeAnswers) {
          assert.ok(events.findIndex(e => e.text?.startsWith('ANSWER ')) > events.findLastIndex(e => e.image),
            'answer was drawn before all image options');
        }
      }
    }
  } else {
    throw new Error('unknown regression mode');
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
