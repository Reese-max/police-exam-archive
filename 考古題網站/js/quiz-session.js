/* === quiz-session.js — local checkpoint for one in-progress mock exam === */
(function (window) {
  'use strict';

  var KEY = 'exam-quiz-active';
  var VERSION = 1;
  var MAX_AGE_MS = 24 * 60 * 60 * 1000;
  var MAX_QUESTIONS = 200;

  function isInt(value) {
    return typeof value === 'number' && isFinite(value) && Math.floor(value) === value;
  }

  function newSessionId() {
    try {
      if (window.crypto && typeof window.crypto.randomUUID === 'function') return window.crypto.randomUUID();
    } catch (error) {}
    return Date.now().toString(36) + '-' + Math.random().toString(36).slice(2);
  }

  /* Questions are escaped before they are rendered with innerHTML. */
  function isSafeText(value) {
    return typeof value === 'string' && !/[<>]/.test(value);
  }

  function isValidQuestion(question) {
    return question && typeof question === 'object' &&
      isSafeText(question.subj) && isSafeText(question.stem) &&
      Array.isArray(question.opts) && question.opts.length === 4 &&
      question.opts.every(isSafeText) &&
      isInt(question.ans) && question.ans >= 0 && question.ans <= 3;
  }

  function validate(checkpoint, now) {
    now = typeof now === 'number' ? now : Date.now();
    if (!checkpoint || typeof checkpoint !== 'object' || checkpoint.v !== VERSION) return false;
    if (typeof checkpoint.sessionId !== 'string' || checkpoint.sessionId.length < 8) return false;
    if (!isInt(checkpoint.savedAt) || checkpoint.savedAt <= 0 || checkpoint.savedAt > now + 60000) return false;
    if (now - checkpoint.savedAt > MAX_AGE_MS) return false;

    if (!Array.isArray(checkpoint.questions) || checkpoint.questions.length === 0 ||
        checkpoint.questions.length > MAX_QUESTIONS || !checkpoint.questions.every(isValidQuestion)) return false;
    var count = checkpoint.questions.length;
    if (!Array.isArray(checkpoint.answers) || checkpoint.answers.length !== count ||
        !checkpoint.answers.every(function (answer) {
          return answer === null || (isInt(answer) && answer >= 0 && answer <= 3);
        })) return false;
    if (!Array.isArray(checkpoint.flags) || checkpoint.flags.length !== count ||
        !checkpoint.flags.every(function (flag) { return typeof flag === 'boolean'; })) return false;
    if (!isInt(checkpoint.cur) || checkpoint.cur < 0 || checkpoint.cur >= count) return false;
    if (!isInt(checkpoint.durSec) || checkpoint.durSec < 0) return false;
    if (typeof checkpoint.timed !== 'boolean' || checkpoint.timed !== (checkpoint.durSec > 0)) return false;
    if (!isInt(checkpoint.elapsed) || checkpoint.elapsed < 0) return false;
    if (!isInt(checkpoint.remain) || checkpoint.remain < 0 || checkpoint.remain > checkpoint.durSec) return false;

    if (checkpoint.timed) {
      if (checkpoint.elapsed > checkpoint.durSec || checkpoint.elapsed + checkpoint.remain !== checkpoint.durSec) return false;
    } else if (checkpoint.remain !== 0) {
      return false;
    }
    return true;
  }

  function save(state) {
    if (!state || typeof state.sessionId !== 'string') return false;
    try {
      if (!state.force) {
        var current = localStorage.getItem(KEY);
        var currentCheckpoint = current ? JSON.parse(current) : null;
        if (!currentCheckpoint || currentCheckpoint.sessionId !== state.sessionId) return false;
      }
      localStorage.setItem(KEY, JSON.stringify({
        v: VERSION,
        savedAt: Date.now(),
        sessionId: state.sessionId,
        timed: !!state.timed,
        questions: state.questions,
        answers: state.answers,
        flags: state.flags,
        cur: state.cur,
        durSec: state.durSec,
        remain: state.remain,
        elapsed: state.elapsed,
      }));
      return true;
    } catch (error) {
      // Private browsing and a full storage quota must not interrupt an exam.
      return false;
    }
  }

  function clear(sessionId) {
    try {
      if (typeof sessionId !== 'string') {
        localStorage.removeItem(KEY);
        return;
      }
      var current = localStorage.getItem(KEY);
      var checkpoint = current ? JSON.parse(current) : null;
      if (checkpoint && checkpoint.sessionId === sessionId) localStorage.removeItem(KEY);
    } catch (error) {}
  }

  function load(now) {
    now = typeof now === 'number' ? now : Date.now();
    var raw;
    try { raw = localStorage.getItem(KEY); } catch (error) { return null; }
    if (!raw) return null;

    var checkpoint;
    try { checkpoint = JSON.parse(raw); } catch (error) { clear(); return null; }
    if (!validate(checkpoint, now)) { clear(); return null; }

    var away = Math.max(0, Math.floor((now - checkpoint.savedAt) / 1000));
    checkpoint.elapsed += away;
    if (checkpoint.timed) {
      checkpoint.remain = Math.max(0, checkpoint.remain - away);
      checkpoint.expired = checkpoint.remain === 0;
    } else {
      checkpoint.expired = false;
    }
    return checkpoint;
  }

  window.QuizSession = {
    KEY: KEY,
    VERSION: VERSION,
    MAX_AGE_MS: MAX_AGE_MS,
    newSessionId: newSessionId,
    save: save,
    load: load,
    clear: clear,
    validate: validate,
  };
})(window);
