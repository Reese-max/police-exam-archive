/* === quiz-engine.js — 模擬考試引擎 === */
(function (window) {
  'use strict';

  var state = {
    questions: [], answers: {}, marked: {}, current: 0,
    timer: null, secondsLeft: 0, totalSeconds: 0, started: false, finished: false
  };

  function prepareQuiz(opts) {
    var filters = {
      cat: opts.cat || '', yr: opts.yr ? parseInt(opts.yr, 10) : null,
      sub: opts.sub || '', type: 'choice', ans: ''
    };
    var pool = SearchEngine.search('', filters, 99999).filter(function (question) {
      return question.optA && question.optB && question.optC && question.optD &&
        AnswerUtils.parse(question.ans).accepted.length > 0;
    });
    var count = Math.min(opts.count || 20, pool.length);
    var shuffled = pool.slice();
    for (var i = shuffled.length - 1; i > 0; i--) {
      var j = Math.floor(Math.random() * (i + 1));
      var temporary = shuffled[i]; shuffled[i] = shuffled[j]; shuffled[j] = temporary;
    }
    state.questions = shuffled.slice(0, count);
    state.answers = {}; state.marked = {}; state.current = 0;
    state.started = false; state.finished = false;
    return { total: state.questions.length, poolSize: pool.length };
  }

  function startQuiz(minutes) {
    state.started = true; state.finished = false;
    state.totalSeconds = minutes * 60; state.secondsLeft = state.totalSeconds;
    startTimer();
  }

  function startTimer() {
    if (state.timer) clearInterval(state.timer);
    state.timer = setInterval(function () {
      state.secondsLeft--;
      if (state.secondsLeft <= 0) {
        state.secondsLeft = 0; clearInterval(state.timer); state.timer = null; finishQuiz();
      }
      if (typeof window.onTick === 'function') window.onTick(state.secondsLeft, state.totalSeconds);
    }, 1000);
  }

  function answer(index, letter) { if (!state.finished) state.answers[index] = letter; }
  function toggleMark(index) { if (state.marked[index]) delete state.marked[index]; else state.marked[index] = true; }
  function goTo(index) { if (index >= 0 && index < state.questions.length) state.current = index; }
  function next() { goTo(state.current + 1); }
  function prev() { goTo(state.current - 1); }

  function finishQuiz() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    state.finished = true;
    var correct = 0, wrong = 0, unanswered = 0, wrongList = [];
    state.questions.forEach(function (question, index) {
      var chosen = state.answers[index];
      var contract = AnswerUtils.parse(question.ans);
      if (contract.bonus) { correct++; return; }
      if (!chosen) { unanswered++; return; }
      if (AnswerUtils.accepts(question.ans, chosen)) correct++;
      else { wrong++; wrongList.push({ idx: index, question: question, chosen: chosen }); }
    });
    var elapsed = state.totalSeconds - state.secondsLeft;
    return {
      correct: correct, wrong: wrong, unanswered: unanswered, total: state.questions.length,
      pct: state.questions.length ? Math.round(correct / state.questions.length * 100) : 0,
      elapsed: elapsed, wrongList: wrongList
    };
  }

  function getState() { return state; }
  function getQuestion(index) { return state.questions[index] || null; }
  function getCurrentQuestion() { return state.questions[state.current] || null; }
  function getAnswer(index) { return state.answers[index]; }
  function isMarked(index) { return !!state.marked[index]; }

  function saveHistory(result) {
    // Ledger failures must reach the caller so submission can be retried.
    if (window.AttemptLedger && state.questions.length) {
      var answers = state.questions.map(function (_, i) { return state.answers[i]; });
      var marked = state.questions.map(function (_, i) { return !!state.marked[i]; });
      var datasetVersion = window.SearchEngine && typeof window.SearchEngine.getDatasetVersion === 'function'
        ? window.SearchEngine.getDatasetVersion()
        : undefined;
      var questions = state.questions.map(function (question) {
        return datasetVersion ? Object.assign({}, question, { datasetVersion: datasetVersion }) : question;
      });
      window.AttemptLedger.recordQuiz({
        questions: questions,
        answers: answers,
        marked: marked,
        quizMode: 'official',
      });
    }
    try {
      var history = JSON.parse(localStorage.getItem('exam-quiz-history') || '[]');
      history.unshift({ date: new Date().toISOString(), correct: result.correct, total: result.total, pct: result.pct, elapsed: result.elapsed });
      localStorage.setItem('exam-quiz-history', JSON.stringify(history.slice(0, 50)));
    } catch (error) {}
  }
  function getHistory() { try { return JSON.parse(localStorage.getItem('exam-quiz-history') || '[]'); } catch (error) { return []; } }

  window.QuizEngine = {
    prepareQuiz: prepareQuiz, startQuiz: startQuiz, answer: answer, toggleMark: toggleMark,
    goTo: goTo, next: next, prev: prev, finishQuiz: finishQuiz,
    getState: getState, getQuestion: getQuestion, getCurrentQuestion: getCurrentQuestion,
    getAnswer: getAnswer, isMarked: isMarked, saveHistory: saveHistory, getHistory: getHistory
  };
})(window);
