"""Exercise the real practice click handler, including its nested source link."""

from pathlib import Path
import subprocess


ROOT = Path(__file__).resolve().parents[1]


def test_source_link_does_not_submit_practice_answer():
    script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('考古題網站/js/app.js', 'utf8');
const start = source.indexOf('function bindOptionClicks()');
const end = source.indexOf('function updateScoreUI()', start);
assert.ok(start >= 0 && end > start);
let handler;
const classes = new Set();
const block = {
  classList: {contains: x => classes.has(x), add: x => classes.add(x)},
  getAttribute: () => 'A', querySelector: () => null,
};
const option = {
  addEventListener: (type, callback) => {assert.equal(type, 'click'); handler = callback;},
  closest: () => block, getAttribute: () => 'A', classList: {add() {}},
};
const context = {document: {querySelectorAll: () => [option]}, practiceMode: true,
  practiceTotal: 0, practiceCorrect: 0, writes: 0,
  updateScoreUI() {}, savePracticeSession() {context.writes++;}};
vm.createContext(context);
vm.runInContext(source.slice(start, end), context);
context.bindOptionClicks();
handler({target: {closest: () => ({tagName: 'A'})}});
assert.equal(context.practiceTotal, 0, 'opening a source image submitted an answer');
assert.equal(context.writes, 0, 'opening a source image persisted an answer');
assert.equal(classes.has('answered'), false);
handler({target: {closest: () => null}});
assert.equal(context.practiceTotal, 1, 'the normal option click must still submit');
assert.equal(context.practiceCorrect, 1);
assert.equal(context.writes, 1);
assert.equal(classes.has('answered'), true);
'''
    result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr


def test_bonus_and_alternative_answers_score_like_answer_utils():
    """送分題任選皆對；「A或C」任一可接受選項皆對，答錯揭示所有正解。"""
    script = r'''
const fs = require('node:fs');
const vm = require('node:vm');
const assert = require('node:assert/strict');
const source = fs.readFileSync('考古題網站/js/app.js', 'utf8');
const start = source.indexOf('function bindOptionClicks()');
const end = source.indexOf('function updateScoreUI()', start);
assert.ok(start >= 0 && end > start);
const snippet = source.slice(start, end);
function run(answer, chosen) {
  const optionClasses = new Set();
  const revealed = [];
  let handler;
  const block = {
    classList: {contains: () => false, add() {}},
    getAttribute: () => answer,
    querySelector: () => null,
    querySelectorAll: () => ['A', 'B', 'C', 'D'].map(v => ({
      getAttribute: () => v,
      classList: {add(x) { if (x === 'correct-reveal') revealed.push(v); }},
    })),
  };
  const option = {
    addEventListener: (type, callback) => { handler = callback; },
    closest: () => block,
    getAttribute: () => chosen,
    classList: {add: x => optionClasses.add(x)},
  };
  const context = {document: {querySelectorAll: () => [option]}, practiceMode: true,
    practiceTotal: 0, practiceCorrect: 0,
    updateScoreUI() {}, savePracticeSession() {}};
  vm.createContext(context);
  vm.runInContext(snippet, context);
  context.bindOptionClicks();
  handler({target: {closest: () => null}});
  return {practiceCorrect: context.practiceCorrect, practiceTotal: context.practiceTotal,
    classes: [...optionClasses], revealed};
}
for (const chosen of ['A', 'B', 'C', 'D']) {
  const row = run('送分', chosen);
  assert.equal(row.practiceCorrect, 1, `送分題選 ${chosen} 應算對`);
  assert.ok(row.classes.includes('correct'), `送分題選 ${chosen} 應標 correct`);
}
for (const chosen of ['A', 'C']) {
  const row = run('A或C', chosen);
  assert.equal(row.practiceCorrect, 1, `A或C 選 ${chosen} 應算對`);
  assert.ok(row.classes.includes('correct'), `A或C 選 ${chosen} 應標 correct`);
}
const wrong = run('A或C', 'B');
assert.equal(wrong.practiceCorrect, 0, 'A或C 選 B 應算錯');
assert.ok(wrong.classes.includes('wrong'), 'A或C 選 B 應標 wrong');
assert.deepEqual(wrong.revealed.sort(), ['A', 'C'], '答錯應揭示所有可接受選項');
const single = run('C', 'C');
assert.equal(single.practiceCorrect, 1, '單選答對仍應算對');
const singleWrong = run('C', 'A');
assert.equal(singleWrong.practiceCorrect, 0, '單選答錯仍應算錯');
assert.deepEqual(singleWrong.revealed, ['C'], '單選答錯應揭示正解');
const bonusWrongImpossible = run('送分', 'B');
assert.deepEqual(bonusWrongImpossible.revealed, [], '送分題不應有 correct-reveal');
for (const bad of ['X', '', '解析']) {
  const row = run(bad, 'A');
  assert.equal(row.practiceCorrect, 0, `無效答案 ${bad} 不應算對`);
  assert.ok(row.classes.includes('wrong'), `無效答案 ${bad} 應標 wrong`);
  assert.deepEqual(row.revealed, [], `無效答案 ${bad} 不應揭示任何選項`);
}
// 已載入 AnswerUtils 時應直接採用其契約（此處以樁證明委派分支有作用）。
const delegated = (() => {
  const optionClasses = new Set();
  let handler;
  const block = {
    classList: {contains: () => false, add() {}},
    getAttribute: () => 'C',
    querySelector: () => null,
    querySelectorAll: () => [],
  };
  const option = {
    addEventListener: (type, callback) => { handler = callback; },
    closest: () => block,
    getAttribute: () => 'B',
    classList: {add: x => optionClasses.add(x)},
  };
  const calls = [];
  const context = {document: {querySelectorAll: () => [option]}, practiceMode: true,
    practiceTotal: 0, practiceCorrect: 0,
    AnswerUtils: {parse(raw) { calls.push(raw); return {accepted: ['B']}; }},
    updateScoreUI() {}, savePracticeSession() {}};
  vm.createContext(context);
  vm.runInContext(snippet, context);
  context.bindOptionClicks();
  handler({target: {closest: () => null}});
  return {practiceCorrect: context.practiceCorrect, calls};
})();
assert.deepEqual(delegated.calls, ['C'], '應以原始答案呼叫 AnswerUtils.parse');
assert.equal(delegated.practiceCorrect, 1, '委派分支應採用 AnswerUtils 的 accepted 計分');
'''
    result = subprocess.run(['node', '-e', script], cwd=ROOT, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
