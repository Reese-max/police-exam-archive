'use strict';

const assert = require('node:assert/strict');
const AnswerUtils = require('../js/answer-utils.js');

assert.deepEqual(AnswerUtils.acceptedAnswers('A或C'), ['A', 'C']);
assert.deepEqual(AnswerUtils.acceptedAnswers('Ａ 或 Ｃ 或 Ｄ'), ['A', 'C', 'D']);
assert.equal(AnswerUtils.isCorrect('A', 'A或C'), true);
assert.equal(AnswerUtils.isCorrect('C', 'A或C'), true);
assert.equal(AnswerUtils.isCorrect('B', 'A或C'), false);
assert.equal(AnswerUtils.isBonus('送分'), true);
assert.equal(AnswerUtils.isBonus('*'), true);
assert.equal(AnswerUtils.isCorrect(null, '送分'), true);
assert.equal(AnswerUtils.display('A或C或D'), 'A、C、D');
assert.equal(AnswerUtils.display('送分'), '送分');
assert.equal(AnswerUtils.isValid(''), false);

console.log('answer-utils semantics passed');
