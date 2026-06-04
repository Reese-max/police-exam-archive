/* === quiz-engine.js — 模擬考試引擎 === */
/* 依賴：search-engine.js（需先載入 search-index.json） */
(function (window) {
  'use strict';

  var state = {
    questions: [],    // 本輪抽到的題目
    answers: {},      // { idx: chosenLetter }
    marked: {},       // { idx: true } 標記回顧
    current: 0,       // 當前題號 index
    timer: null,      // setInterval id
    secondsLeft: 0,   // 剩餘秒數
    totalSeconds: 0,  // 總秒數
    started: false,
    finished: false,
  };

  /* ── 抽題 ── */
  function prepareQuiz(opts) {
    // opts: { cat, yr, sub, count }
    var filters = {
      cat: opts.cat || '',
      yr: opts.yr ? parseInt(opts.yr, 10) : null,
      sub: opts.sub || '',
      type: 'choice',  // 模擬考試只出選擇題
      ans: '',          // 不篩選答案
    };

    var pool = SearchEngine.search('', filters, 9999);

    // 隨機抽題
    var count = Math.min(opts.count || 20, pool.length);
    var shuffled = pool.slice();
    for (var i = shuffled.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var tmp = shuffled[i]; shuffled[i] = shuffled[j]; shuffled[j] = tmp;
    }
    state.questions = shuffled.slice(0, count);
    state.answers = {};
    state.marked = {};
    state.current = 0;
    state.started = false;
    state.finished = false;

    return { total: state.questions.length, poolSize: pool.length };
  }

  /* ── 開始考試 ── */
  function startQuiz(minutes) {
    state.started = true;
    state.finished = false;
    state.totalSeconds = minutes * 60;
    state.secondsLeft = state.totalSeconds;
    _startTimer();
  }

  function _startTimer() {
    if (state.timer) clearInterval(state.timer);
    state.timer = setInterval(function () {
      state.secondsLeft--;
      if (state.secondsLeft <= 0) {
        state.secondsLeft = 0;
        clearInterval(state.timer);
        state.timer = null;
        finishQuiz();
      }
      if (typeof window.onTick === 'function') {
        window.onTick(state.secondsLeft, state.totalSeconds);
      }
    }, 1000);
  }

  /* ── 作答 ── */
  function answer(idx, letter) {
    if (state.finished) return;
    state.answers[idx] = letter;
  }

  /* ── 標記回顧 ── */
  function toggleMark(idx) {
    if (state.marked[idx]) delete state.marked[idx];
    else state.marked[idx] = true;
  }

  /* ── 導航 ── */
  function goTo(idx) {
    if (idx >= 0 && idx < state.questions.length) state.current = idx;
  }
  function next() { goTo(state.current + 1); }
  function prev() { goTo(state.current - 1); }

  /* ── 交卷 ── */
  function finishQuiz() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    state.finished = true;

    var correct = 0, wrong = 0, unanswered = 0;
    var wrongList = [];

    state.questions.forEach(function (q, i) {
      var chosen = state.answers[i];
      if (!chosen) { unanswered++; return; }
      if (chosen === q.ans) {
        correct++;
      } else {
        wrong++;
        wrongList.push({ idx: i, question: q, chosen: chosen });
      }
    });

    var elapsed = state.totalSeconds - state.secondsLeft;

    return {
      correct: correct,
      wrong: wrong,
      unanswered: unanswered,
      total: state.questions.length,
      pct: state.questions.length > 0 ? Math.round(correct / state.questions.length * 100) : 0,
      elapsed: elapsed,
      wrongList: wrongList,
    };
  }

  /* ── 讀取 ── */
  function getState() { return state; }
  function getQuestion(idx) { return state.questions[idx] || null; }
  function getCurrentQuestion() { return state.questions[state.current] || null; }
  function getAnswer(idx) { return state.answers[idx]; }
  function isMarked(idx) { return !!state.marked[idx]; }

  /* ── 歷史紀錄 ── */
  function saveHistory(result) {
    try {
      var history = JSON.parse(localStorage.getItem('exam-quiz-history') || '[]');
      history.unshift({
        date: new Date().toISOString(),
        correct: result.correct,
        total: result.total,
        pct: result.pct,
        elapsed: result.elapsed,
      });
      if (history.length > 50) history = history.slice(0, 50);
      localStorage.setItem('exam-quiz-history', JSON.stringify(history));
    } catch (e) {}
  }

  function getHistory() {
    try { return JSON.parse(localStorage.getItem('exam-quiz-history') || '[]'); }
    catch (e) { return []; }
  }

  /* ── 匯出 ── */
  window.QuizEngine = {
    prepareQuiz: prepareQuiz,
    startQuiz: startQuiz,
    answer: answer,
    toggleMark: toggleMark,
    goTo: goTo,
    next: next,
    prev: prev,
    finishQuiz: finishQuiz,
    getState: getState,
    getQuestion: getQuestion,
    getCurrentQuestion: getCurrentQuestion,
    getAnswer: getAnswer,
    isMarked: isMarked,
    saveHistory: saveHistory,
    getHistory: getHistory,
  };
})(window);
