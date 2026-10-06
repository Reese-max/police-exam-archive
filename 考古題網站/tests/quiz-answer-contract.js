'use strict';
// AnswerUtils contract loaded before QuizEngine.
const assert = require('assert');
const fs = require('fs');
const vm = require('vm');

const storage = new Map();
const context = {
  console,
  setInterval: function () { return 1; },
  clearInterval: function () {},
  localStorage: {
    getItem: function (key) { return storage.has(key) ? storage.get(key) : null; },
    setItem: function (key, value) { storage.set(key, String(value)); },
  },
};
context.window = context;
vm.createContext(context);
vm.runInContext(
  fs.readFileSync('考古題網站/js/answer-utils.js', 'utf8'),
  context,
  { filename: 'answer-utils.js' }
);
vm.runInContext(
  fs.readFileSync('考古題網站/js/quiz-engine.js', 'utf8'),
  context,
  { filename: 'quiz-engine.js' }
);

assert.ok(context.AnswerUtils, 'AnswerUtils must be exported');
assert.ok(context.QuizEngine, 'QuizEngine must be exported');

function grade(answer, chosen) {
  const state = context.QuizEngine.getState();
  state.questions = [{ ans: answer }];
  state.answers = chosen ? { 0: chosen } : {};
  state.marked = {};
  state.current = 0;
  state.timer = null;
  state.secondsLeft = 30;
  state.totalSeconds = 60;
  state.started = true;
  state.finished = false;
  return context.QuizEngine.finishQuiz();
}

assert.deepStrictEqual(
  Array.from(context.AnswerUtils.parse('A或C').accepted),
  ['A', 'C']
);
assert.strictEqual(grade('A或C', 'A').correct, 1);
assert.strictEqual(grade('A或C', 'C').correct, 1);
assert.strictEqual(grade('A或C', 'B').wrong, 1);
assert.strictEqual(grade('A或C或D', 'D').correct, 1);
assert.strictEqual(grade('送分', 'B').correct, 1);
console.log('quiz answer contract passed');
