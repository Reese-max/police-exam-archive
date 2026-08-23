'use strict';

const assert = require('node:assert/strict');

global.window = global;

class FakeMiniSearch {
  constructor(options) {
    this.options = options;
    this.documents = [];
  }

  addAll(documents) {
    this.documents = documents.slice();
  }

  search(query) {
    const needle = String(query || '').toLowerCase();
    return this.documents
      .filter((document) => {
        if (!needle) return true;
        return ['stem', 'passage', 'optA', 'optB', 'optC', 'optD', 'sub']
          .some((field) => String(document[field] || '').toLowerCase().includes(needle));
      })
      .map((document) => ({ id: document.id, score: 1 }));
  }
}

global.MiniSearch = FakeMiniSearch;

const data = {
  v: 2,
  fields: ['cat', 'cats', 'yr', 'sub', 'no', 'type', 'stem', 'passage', 'optA', 'optB', 'optC', 'optD', 'ans'],
  stats: { total: 2, choice: 2, essay: 0, categories: 2, subjects: 1 },
  facets: { categories: ['行政警察學系', '資訊管理學系'], subjects: ['共同英文'], years: [115] },
  columns: {
    cat: ['行政警察學系', '行政警察學系'],
    cats: [['行政警察學系', '資訊管理學系'], ['行政警察學系']],
    yr: [115, 115],
    sub: ['共同英文', '共同英文'],
    no: ['51', '60'],
    type: ['choice', 'choice'],
    stem: ['請依上文作答', '責任轉移'],
    passage: ['Zero Trust reading passage', ''],
    optA: ['targeting', 'A option'],
    optB: ['haunting', 'B option'],
    optC: ['ignoring', 'C option'],
    optD: ['staring', 'D option'],
    ans: ['A或C', '送分']
  }
};

global.fetch = async function () {
  return { ok: true, json: async () => data };
};

require('../js/search-engine.js');

(async function run() {
  const stats = await global.SearchEngine.loadIndex('');
  assert.equal(stats.total, 2);
  assert.equal(global.SearchEngine.getVersion(), 2);

  const byMembership = global.SearchEngine.search('', { cat: '資訊管理學系', type: 'choice' }, 10);
  assert.equal(byMembership.length, 1);
  assert.equal(byMembership[0].no, '51');
  assert.deepEqual(byMembership[0].cats, ['行政警察學系', '資訊管理學系']);

  const byPassage = global.SearchEngine.search('Zero Trust', {}, 10);
  assert.equal(byPassage.length, 1);
  assert.equal(byPassage[0].passage, 'Zero Trust reading passage');

  const byAcceptedAnswer = global.SearchEngine.search('', { ans: 'C' }, 10);
  assert.equal(byAcceptedAnswer.length, 1);
  assert.equal(byAcceptedAnswer[0].ans, 'A或C');

  const bonus = global.SearchEngine.search('', { ans: '送分' }, 10);
  assert.equal(bonus.length, 1);
  assert.equal(bonus[0].no, '60');

  console.log('search-engine v2 semantics passed');
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
