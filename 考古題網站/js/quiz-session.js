/* === quiz-session.js — 模擬考試進行中 checkpoint（localStorage） === */
/* 供 quiz.html 使用：儲存/驗證/恢復單一進行中考試，交卷或捨棄後清除。 */
(function (window) {
  'use strict';

  var KEY = 'exam-quiz-active';
  var VERSION = 1;
  var MAX_AGE_MS = 24 * 60 * 60 * 1000; // checkpoint 最長保留 24 小時，逾期視為 stale
  var MAX_QUESTIONS = 200;              // 上限防呆（本頁最多 50 題）

  /* ── 儲存 ── */
  function save(state) {
    try {
      var cp = {
        v: VERSION,
        savedAt: Date.now(),
        timed: !!state.timed,
        questions: state.questions,
        answers: state.answers,
        flags: state.flags,
        cur: state.cur,
        durSec: state.durSec,
        remain: state.remain,
        elapsed: state.elapsed,
      };
      localStorage.setItem(KEY, JSON.stringify(cp));
    } catch (e) {}
  }

  /* ── 驗證 ── */
  function _isInt(n) { return typeof n === 'number' && isFinite(n) && Math.floor(n) === n; }
  // v1 題目由 buildQuestions escape 後儲存；不可讓 checkpoint 繞過 HTML 邊界。
  function _validText(s) { return typeof s === 'string' && !/[<>]/.test(s); }

  function _validQuestion(q) {
    return q && typeof q === 'object' &&
      _validText(q.subj) && _validText(q.stem) &&
      Array.isArray(q.opts) && q.opts.length === 4 &&
      q.opts.every(_validText) &&
      _isInt(q.ans) && q.ans >= 0 && q.ans <= 3;
  }

  function validate(cp, now) {
    now = typeof now === 'number' ? now : Date.now();
    if (!cp || typeof cp !== 'object' || cp.v !== VERSION) return false;
    if (!_isInt(cp.savedAt) || cp.savedAt <= 0 || cp.savedAt > now + 60000) return false;
    if (now - cp.savedAt > MAX_AGE_MS) return false;
    if (!Array.isArray(cp.questions) || cp.questions.length === 0 ||
        cp.questions.length > MAX_QUESTIONS || !cp.questions.every(_validQuestion)) return false;
    var n = cp.questions.length;
    if (!Array.isArray(cp.answers) || cp.answers.length !== n ||
        !cp.answers.every(function (a) { return a === null || (_isInt(a) && a >= 0 && a <= 3); })) return false;
    if (!Array.isArray(cp.flags) || cp.flags.length !== n ||
        !cp.flags.every(function (f) { return typeof f === 'boolean'; })) return false;
    if (!_isInt(cp.cur) || cp.cur < 0 || cp.cur >= n) return false;
    if (!_isInt(cp.durSec) || cp.durSec < 0) return false;
    if (typeof cp.timed !== 'boolean' || cp.timed !== (cp.durSec > 0)) return false;
    if (!_isInt(cp.elapsed) || cp.elapsed < 0) return false;
    if (!_isInt(cp.remain) || cp.remain < 0 || cp.remain > cp.durSec) return false;
    return true;
  }

  /* ── 讀取（含牆鐘補償：考試時鐘在中斷期間視為繼續走） ── */
  function load(now) {
    now = typeof now === 'number' ? now : Date.now();
    var raw;
    try { raw = localStorage.getItem(KEY); } catch (e) { return null; }
    if (!raw) return null;
    var cp;
    try { cp = JSON.parse(raw); } catch (e) { clear(); return null; }
    if (!validate(cp, now)) { clear(); return null; }
    var away = Math.max(0, Math.floor((now - cp.savedAt) / 1000));
    if (cp.timed) {
      cp.remain = Math.max(0, cp.remain - away);
      cp.expired = cp.remain === 0;
    } else {
      cp.expired = false;
    }
    cp.elapsed += away;
    return cp;
  }

  /* ── 清除 ── */
  function clear() {
    try { localStorage.removeItem(KEY); } catch (e) {}
  }

  window.QuizSession = {
    KEY: KEY,
    VERSION: VERSION,
    MAX_AGE_MS: MAX_AGE_MS,
    save: save,
    load: load,
    clear: clear,
    validate: validate,
  };
})(window);
