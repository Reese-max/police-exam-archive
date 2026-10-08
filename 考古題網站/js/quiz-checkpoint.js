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
  var VERSION = 2; // v1 單一整數正解仍可載入；新場次保留現代答案/文章/圖片契約。
  var MAX_AGE_MS = 24 * 60 * 60 * 1000;  // 超過 24 小時的檢查點視為過期
  var CLOCK_SKEW_MS = 60 * 1000;         // 容忍的時鐘偏差
  var MAX_QUESTIONS = 200;               // 題目數上限（目前介面最多 50 題）
  var ALLOWED_DUR = { 0: true, 1800: true, 3600: true, 5400: true, 7200: true };  // 不限時 / 30 / 60 / 90 / 120 分

  function _isInt(v) { return typeof v === 'number' && isFinite(v) && Math.floor(v) === v; }
  function _validSessionId(v) { return typeof v === 'string' && /^[a-zA-Z0-9-]{1,100}$/.test(v); }
  var sequence = 0;
  function newSessionId() {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') return crypto.randomUUID();
    return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2) + '-' + (++sequence);
  }

  function _store(storage) {
    if (storage) return storage;
    try { return typeof localStorage !== 'undefined' ? localStorage : null; }
    catch (e) { return null; }
  }

  /* 題目文字於 buildQuestions 已 escape，合法快照不應含原始 < >； */
  /* 拒絕未轉義標記可避免被竄改的 localStorage 快照經 innerHTML 注入 DOM。 */
  function _hasMarkup(s) { return /[<>]/.test(s); }

  // 圖片只能來自網站內的相對資產路徑。拒絕 scheme、外站、跳脫目錄、
  // percent/entity 編碼與引號，避免 localStorage 或索引竄改變成可執行連結。
  function isSafeImagePath(src) {
    if (typeof src !== 'string') return false;
    if (!src) return true;
    if (/[\x00-\x20\x7f:?#%&"'<>\\]/.test(src) || src.charAt(0) === '/') return false;
    var parts = src.split('/');
    if (parts.some(function (p) { return !p || p === '.' || p === '..'; })) return false;
    return /\.(?:png|jpe?g|webp|gif)$/i.test(parts[parts.length - 1]);
  }
  function _validAttribute(v) {
    return typeof v === 'string' && !_hasMarkup(v) && !/[\x00-\x1f\x7f"']/.test(v);
  }
  function _validMedia(m) {
    return !!m && typeof m === 'object' && !Array.isArray(m)
      && isSafeImagePath(m.src) && _validAttribute(m.alt)
      && typeof m.sourcePage === 'string' && /^(?:|[1-9][0-9]{0,3})$/.test(m.sourcePage);
  }
  function _validAnswers(q) {
    if (q.accepted === undefined) return _isInt(q.ans) && q.ans >= 0 && q.ans <= 3;
    if (!Array.isArray(q.accepted) || q.accepted.length < 1 || q.accepted.length > 4 || typeof q.bonus !== 'boolean') return false;
    var seen = {};
    for (var i = 0; i < q.accepted.length; i++) {
      var a = q.accepted[i];
      if (!_isInt(a) || a < 0 || a > 3 || seen[a]) return false;
      seen[a] = true;
    }
    if (q.bonus && q.accepted.length !== 4) return false;
    if (q.answerLabel !== undefined) {
      if (typeof q.answerLabel !== 'string') return false;
      if (q.bonus) return q.answerLabel === '送分';
      if (!/^[ABCD](?:或[ABCD]){0,3}$/.test(q.answerLabel)) return false;
      var labels = q.answerLabel.split('或');
      if (labels.length !== q.accepted.length) return false;
      for (i = 0; i < labels.length; i++) {
        if ('ABCD'.indexOf(labels[i]) !== q.accepted[i]) return false;
      }
    }
    return true;
  }

  function _validQuestion(q) {
    return !!q && typeof q === 'object' && !Array.isArray(q)
      && typeof q.subj === 'string' && !_hasMarkup(q.subj)
      && typeof q.stem === 'string' && !_hasMarkup(q.stem)
      && Array.isArray(q.opts) && q.opts.length === 4
      && q.opts.every(function (o) { return typeof o === 'string' && !_hasMarkup(o); })
      && _validAnswers(q)
      && (q.passage === undefined || (typeof q.passage === 'string' && !_hasMarkup(q.passage)))
      && (q.imageOpts === undefined || (Array.isArray(q.imageOpts) && q.imageOpts.length === 4 && q.imageOpts.every(_validMedia)));
  }

  /* 驗證並正規化一份快照；任何欄位不合法時回傳 null（呼叫端退回設定畫面）。 */
  function validate(snap, now) {
    if (!snap || typeof snap !== 'object' || Array.isArray(snap)) return null;
    now = _isInt(now) ? now : Date.now();
    if (snap.v !== VERSION && snap.v !== 1) return null;
    // 原有 v1 快照沒有 sessionId，仍可回復；回復頁會替它建立識別。
    if (snap.sessionId !== undefined && !_validSessionId(snap.sessionId)) return null;
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
    if (snap.durSec > 0 && snap.elapsed + snap.remain !== snap.durSec) return null;

    return {
      v: snap.v,
      sessionId: snap.sessionId,
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
      sessionId: state.sessionId,
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
  function _owns(store, sessionId) {
    if (!_validSessionId(sessionId)) return false;
    try {
      var current = JSON.parse(store.getItem(KEY));
      return !!current && current.sessionId === sessionId;
    } catch (e) { return false; }
  }
  function _matchesRaw(store, raw) {
    try { return store.getItem(KEY) === raw; } catch (e) { return false; }
  }

  // 新場次首次寫入不帶 expectedSessionId；之後只有目前場次能更新。
  // 若檢查點已被交卷/捨棄清除，舊分頁不得從 pagehide 或 tick 把它寫回。
  function save(state, storage, now, expectedSessionId, expectedRaw) {
    var store = _store(storage);
    if (!store) return false;
    var snap = build(state, now);
    if (!snap) return false;
    // 回復時可持有舊識別並寫入新識別，交接後舊分頁即失去寫入權。
    if (expectedSessionId !== undefined && (!_validSessionId(snap.sessionId) || !_owns(store, expectedSessionId))) return false;
    if (expectedSessionId === undefined && expectedRaw !== undefined && (!_validSessionId(snap.sessionId) || !_matchesRaw(store, expectedRaw))) return false;
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
    // 舊 v1 沒有場次識別；保留讀取時的原始值，供捨棄/逾時清除比對。
    // token 只回傳給呼叫端，不寫進下一份快照，也不改變 savedAt。
    valid.storageToken = raw;
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
  function clear(storage, expectedSessionId, expectedRaw) {
    var store = _store(storage);
    if (!store) return;
    if (expectedSessionId !== undefined && !_owns(store, expectedSessionId)) return;
    if (expectedSessionId === undefined && expectedRaw !== undefined && !_matchesRaw(store, expectedRaw)) return;
    try { store.removeItem(KEY); } catch (e) {}
  }

  return {
    KEY: KEY,
    VERSION: VERSION,
    MAX_AGE_MS: MAX_AGE_MS,
    newSessionId: newSessionId,
    isSafeImagePath: isSafeImagePath,
    validate: validate,
    build: build,
    save: save,
    load: load,
    clear: clear,
  };
});
