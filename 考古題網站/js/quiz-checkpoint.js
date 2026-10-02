/* === quiz-checkpoint.js — 模擬考試進行中場次的本機檢查點 === */
/* 將進行中的考試快照（題目、作答、標記、位置、計時）存入 localStorage， */
/* 供頁面重新載入或分頁/程序中斷後回復。僅使用本機儲存，不涉及帳號、雲端同步或外部服務。 */
(function (root, factory) {
  var api = factory();
  if (typeof module !== 'undefined' && module.exports) { module.exports = api; }
  if (root) { root.QuizCheckpoint = api; }
})(typeof self !== 'undefined' ? self : this, function () {
  'use strict';

  var KEY = 'exam-quiz-active';
  var VERSION = 1;
  var MAX_AGE_MS = 24 * 60 * 60 * 1000;  // 超過 24 小時的檢查點視為過期
  var CLOCK_SKEW_MS = 60 * 1000;         // 容忍的時鐘偏差
  var MAX_QUESTIONS = 200;               // 題目數上限（目前介面最多 50 題）
  var ALLOWED_DUR = { 0: true, 1800: true, 3600: true, 5400: true, 7200: true };  // 不限時 / 30 / 60 / 90 / 120 分

  function _isInt(v) { return typeof v === 'number' && isFinite(v) && Math.floor(v) === v; }

  function _store(storage) {
    if (storage) return storage;
    try { return typeof localStorage !== 'undefined' ? localStorage : null; }
    catch (e) { return null; }
  }

  /* 題目文字於 buildQuestions 已 escape，合法快照不應含原始 < >； */
  /* 拒絕未轉義標記可避免被竄改的 localStorage 快照經 innerHTML 注入 DOM。 */
  function _hasMarkup(s) { return /[<>]/.test(s); }

  function _validQuestion(q) {
    return !!q && typeof q === 'object' && !Array.isArray(q)
      && typeof q.subj === 'string' && !_hasMarkup(q.subj)
      && typeof q.stem === 'string' && !_hasMarkup(q.stem)
      && Array.isArray(q.opts) && q.opts.length === 4
      && q.opts.every(function (o) { return typeof o === 'string' && !_hasMarkup(o); })
      && _isInt(q.ans) && q.ans >= 0 && q.ans <= 3;
  }

  /* 驗證並正規化一份快照；任何欄位不合法時回傳 null（呼叫端退回設定畫面）。 */
  function validate(snap, now) {
    if (!snap || typeof snap !== 'object' || Array.isArray(snap)) return null;
    now = _isInt(now) ? now : Date.now();
    if (snap.v !== VERSION) return null;
    if (!_isInt(snap.savedAt) || snap.savedAt > now + CLOCK_SKEW_MS || now - snap.savedAt > MAX_AGE_MS) return null;

    var qs = snap.questions;
    if (!Array.isArray(qs) || qs.length < 1 || qs.length > MAX_QUESTIONS) return null;
    for (var i = 0; i < qs.length; i++) { if (!_validQuestion(qs[i])) return null; }
    var n = qs.length;

    if (!Array.isArray(snap.answers) || snap.answers.length !== n) return null;
    for (i = 0; i < n; i++) {
      var a = snap.answers[i];
      if (a !== null && !(_isInt(a) && a >= 0 && a < 4)) return null;
    }
    if (!Array.isArray(snap.flags) || snap.flags.length !== n) return null;
    for (i = 0; i < n; i++) { if (snap.flags[i] !== true && snap.flags[i] !== false) return null; }

    if (!_isInt(snap.cur) || snap.cur < 0 || snap.cur >= n) return null;
    if (!_isInt(snap.durSec) || !ALLOWED_DUR[snap.durSec]) return null;
    if (!_isInt(snap.remain) || snap.remain < 0 || snap.remain > snap.durSec) return null;
    if (!_isInt(snap.elapsed) || snap.elapsed < 0) return null;

    return {
      v: VERSION,
      savedAt: snap.savedAt,
      questions: qs.slice(),
      answers: snap.answers.slice(),
      flags: snap.flags.slice(),
      cur: snap.cur,
      durSec: snap.durSec,
      remain: snap.remain,
      elapsed: snap.elapsed,
    };
  }

  /* 由進行中的狀態建立快照；狀態不完整或不合法時回傳 null。 */
  function build(state, now) {
    if (!state || typeof state !== 'object') return null;
    var snap = {
      v: VERSION,
      savedAt: _isInt(now) ? now : Date.now(),
      questions: state.questions,
      answers: state.answers,
      flags: state.flags,
      cur: state.cur,
      durSec: state.durSec,
      remain: state.remain,
      elapsed: state.elapsed,
    };
    return validate(snap, snap.savedAt);
  }

  /* 寫入檢查點；成功回傳 true，狀態不合法或儲存失敗（容量/隱私模式）回傳 false。 */
  function save(state, storage, now) {
    var store = _store(storage);
    if (!store) return false;
    var snap = build(state, now);
    if (!snap) return false;
    try {
      store.setItem(KEY, JSON.stringify(snap));
      return true;
    } catch (e) { return false; }
  }

  /* 讀取並驗證檢查點；缺漏、毀損或過期一律回傳 null 並清除殘留資料。 */
  function load(storage, now) {
    var store = _store(storage);
    if (!store) return null;
    var raw;
    try { raw = store.getItem(KEY); } catch (e) { return null; }
    if (raw === null || raw === undefined) return null;
    var snap = null;
    try { snap = JSON.parse(raw); } catch (e) { snap = null; }
    now = _isInt(now) ? now : Date.now();
    var valid = snap === null ? null : validate(snap, now);
    if (!valid) { clear(store); return null; }
    // 扣除離線期間經過的牆鐘時間，避免重新整理等同於暫停計時；
    // remain 以 0 為下界（離線期間已逾時的考試，回復後會立即交卷）。
    var offline = Math.floor((now - valid.savedAt) / 1000);
    if (offline > 0) {
      valid.elapsed += offline;
      if (valid.durSec > 0) { valid.remain = Math.max(0, valid.remain - offline); }
    }
    return valid;
  }

  /* 明確清除檢查點（交卷或使用者捨棄時呼叫）。 */
  function clear(storage) {
    var store = _store(storage);
    if (!store) return;
    try { store.removeItem(KEY); } catch (e) {}
  }

  return {
    KEY: KEY,
    VERSION: VERSION,
    MAX_AGE_MS: MAX_AGE_MS,
    validate: validate,
    build: build,
    save: save,
    load: load,
    clear: clear,
  };
});
