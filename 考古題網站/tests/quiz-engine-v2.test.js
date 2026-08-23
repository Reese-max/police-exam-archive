'use strict';

const assert = require('node:assert/strict');

global.window = global;
global.AnswerUtils = require('../js/answer-utils.js');
global.SearchEngine = {
  search: function () {
    return [
      { idx: 1, type: 'choice', optA: 'a', optB: 'b', optC: 'c', optD: 'd', ans: 'A或C' },
      { idx: 2, type: 'choice', optA: 'a', optB: 'b', optC: 'c', optD: 'd', ans: '送分' },
      { idx: 3, type: 'choice', optA: 'a', optB: 'b', optC: 'c', optD: 'd', ans: 'D' }
    ];
  }
};

require('../js/quiz-engine.js');

const prepared = global.QuizEngine.prepareQuiz({ count: 3, random: false });
assert.equal(prepared.total, 3);
assert.equal(prepared.poolSize, 3);

global.QuizEngine.answer(0, 'C');
global.QuizEngine.answer(2, 'B');
const result = global.QuizEngine.finishQuiz();

assert.equal(result.correct, 2, 'A或C 的 C 與送分題都應計為正確');
assert.equal(result.wrong, 1);
assert.equal(result.unanswered, 0);
assert.equal(result.bonus, 1);
assert.equal(result.pct, 67);
assert.equal(result.wrongList.length, 1);
assert.equal(result.wrongList[0].chosen, 'B');

console.log('quiz-engine v2 scoring passed');
