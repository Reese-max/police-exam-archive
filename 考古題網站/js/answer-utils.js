/* 共用答案語意：支援單一答案、複數正解與送分題。 */
(function (root, factory) {
  var api = factory();
  if (typeof module === 'object' && module.exports) module.exports = api;
  if (root) root.AnswerUtils = api;
})(typeof globalThis !== 'undefined' ? globalThis : this, function () {
  'use strict';

  var LABELS = ['A', 'B', 'C', 'D'];

  function normalize(value) {
    if (value === null || value === undefined) return '';
    return String(value).normalize('NFKC').toUpperCase().replace(/\s+/g, '');
  }

  function isBonus(answer) {
    var value = normalize(answer);
    return value === '*' || value.indexOf('送分') !== -1 || value.indexOf('一律給分') !== -1;
  }

  function acceptedAnswers(answer) {
    if (isBonus(answer)) return LABELS.slice();
    var value = normalize(answer);
    var result = [];
    value.replace(/[A-D]/g, function (letter) {
      if (result.indexOf(letter) === -1) result.push(letter);
      return letter;
    });
    return result;
  }

  function isValid(answer) {
    return isBonus(answer) || acceptedAnswers(answer).length > 0;
  }

  function isCorrect(chosen, answer) {
    if (isBonus(answer)) return true;
    var value = normalize(chosen);
    return value.length > 0 && acceptedAnswers(answer).indexOf(value.charAt(0)) !== -1;
  }

  function display(answer) {
    if (isBonus(answer)) return '送分';
    return acceptedAnswers(answer).join('、');
  }

  return {
    LABELS: LABELS.slice(),
    normalize: normalize,
    isBonus: isBonus,
    acceptedAnswers: acceptedAnswers,
    isValid: isValid,
    isCorrect: isCorrect,
    display: display,
  };
});
