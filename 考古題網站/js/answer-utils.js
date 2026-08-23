/* === answer-utils.js — 官方答案契約 === */
(function (window) {
  'use strict';

  function parse(raw) {
    var value = String(raw || '').trim().toUpperCase();
    if (value === '送分') return { accepted: ['A','B','C','D'], bonus: true };
    var accepted = [];
    value.split('或').forEach(function (letter) {
      if ('ABCD'.indexOf(letter) !== -1 && accepted.indexOf(letter) === -1) accepted.push(letter);
    });
    return { accepted: accepted, bonus: false };
  }

  function accepts(raw, chosen) {
    var contract = parse(raw);
    return contract.bonus || contract.accepted.indexOf(String(chosen || '').toUpperCase()) !== -1;
  }

  window.AnswerUtils = { parse: parse, accepts: accepts };
})(window);
