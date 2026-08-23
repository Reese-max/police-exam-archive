const fs = require('fs'), path = require('path');
const root = __dirname;
const input = process.argv[2] || path.join(root, 'data', 'analytics.json');
const output = process.argv[3] || path.join(root, 'analytics-chart-data.js');
const a = JSON.parse(fs.readFileSync(input, 'utf8'));

const YEARS = a.stats.years.map(String);
const ALL_YEAR = YEARS.map(y => a.year_totals[y] || 0);

const ad = a.answer_distribution || {};
const abcd = ['A', 'B', 'C', 'D'].map(k => ad[k] || 0);
const sumABCD = abcd.reduce((s, x) => s + x, 0) || 1;
const ALL_DONUT = abcd.map(x => +(x / sumABCD * 100).toFixed(1));

const cats = Object.keys(a.category_totals)
  .map(name => ({ name, total: a.category_totals[name] }))
  .sort((x, y) => y.total - x.total)
  .slice(0, 15);

const CATEGORIES = cats.map((c, i) => ({
  id: 'c' + i,
  name: c.name,
  total: c.total,
  year: YEARS.map(y => (a.by_category[c.name] && a.by_category[c.name][y]) || 0),
  donut: ALL_DONUT,
}));

const TREND_CATS = CATEGORIES.slice(0, 5).map(c => c.id);
const KEYWORDS = (a.top_keywords || []).slice(0, 50).map(k => [k.word, k.count]);
const STATS = {
  total: a.stats.total_questions,
  choice: a.stats.choice_questions,
  essay: a.stats.essay_questions,
  categories: a.stats.categories,
  subjects: a.stats.subjects,
  firstYear: Math.min(...a.stats.years),
  lastYear: Math.max(...a.stats.years),
  yearCount: a.stats.years.length,
};

const out = `/* ===== 真實資料（由 analytics.json 自動產生，勿手改） ===== */\nconst STATS = ${JSON.stringify(STATS)};\nconst YEARS = ${JSON.stringify(YEARS)};\nconst CATEGORIES = ${JSON.stringify(CATEGORIES)};\nconst ALL_YEAR = ${JSON.stringify(ALL_YEAR)};\nconst ALL_DONUT = ${JSON.stringify(ALL_DONUT)};\nconst KEYWORDS = ${JSON.stringify(KEYWORDS)};\nconst TREND_CATS = ${JSON.stringify(TREND_CATS)};\n`;
fs.writeFileSync(output, out, 'utf8');
console.log(JSON.stringify({ STATS, YEARS, ALL_YEAR, catCount: CATEGORIES.length, kwCount: KEYWORDS.length }));
