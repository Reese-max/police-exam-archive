const fs = require('fs'), path = require('path');
const root = __dirname; // 本腳本位於 考古題網站/ 內，路徑相對自身
const a = JSON.parse(fs.readFileSync(path.join(root, 'data', 'analytics.json'), 'utf8'));

const YEARS = a.stats.years.map(String);
const ALL_YEAR = YEARS.map(y => a.year_totals[y] || 0);

const ad = a.answer_distribution || {};
const abcd = ['A', 'B', 'C', 'D'].map(k => ad[k] || 0);
const sumABCD = abcd.reduce((s, x) => s + x, 0) || 1;
const ALL_DONUT = abcd.map(x => +(x / sumABCD * 100).toFixed(1));

// 前 15 大類科（依累計題數），保留圖表可讀性
const cats = Object.keys(a.category_totals)
  .map(name => ({ name, total: a.category_totals[name] }))
  .sort((x, y) => y.total - x.total)
  .slice(0, 15);

const CATEGORIES = cats.map((c, i) => ({
  id: 'c' + i,
  name: c.name,
  total: c.total,
  year: YEARS.map(y => (a.by_category[c.name] && a.by_category[c.name][y]) || 0),
  donut: ALL_DONUT, // analytics.json 無 per-category 答案分佈，用全站比例近似
}));

const TREND_CATS = CATEGORIES.slice(0, 5).map(c => c.id);
const KEYWORDS = (a.top_keywords || []).slice(0, 50).map(k => [k.word, k.count]);

const out = `/* ===== 真實資料（由 data/analytics.json 自動產生，勿手改） ===== */
const YEARS = ${JSON.stringify(YEARS)};
const CATEGORIES = ${JSON.stringify(CATEGORIES)};
const ALL_YEAR = ${JSON.stringify(ALL_YEAR)};
const ALL_DONUT = ${JSON.stringify(ALL_DONUT)};
const KEYWORDS = ${JSON.stringify(KEYWORDS)};
const TREND_CATS = ${JSON.stringify(TREND_CATS)};
`;
fs.writeFileSync(path.join(root, 'analytics-chart-data.js'), out, 'utf8');
console.log(JSON.stringify({
  YEARS, ALL_YEAR, ALL_DONUT,
  catCount: CATEGORIES.length,
  topCats: CATEGORIES.slice(0, 6).map(c => c.name + '=' + c.total),
  trendNames: TREND_CATS.map(id => CATEGORIES.find(c => c.id === id).name),
  kwCount: KEYWORDS.length, kw0: KEYWORDS[0], kw49: KEYWORDS[49],
}, null, 0));
