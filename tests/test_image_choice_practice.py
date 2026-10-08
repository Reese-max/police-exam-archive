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
