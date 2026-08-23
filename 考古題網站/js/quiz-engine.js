/* 可重用模擬考引擎；依賴 SearchEngine，建議先載入 AnswerUtils。 */
(function (window) {
  'use strict';

  var state = {
    questions: [],
    answers: {},
    marked: {},
    current: 0,
    timer: null,
    secondsLeft: 0,
    totalSeconds: 0,
    started: false,
    finished: false
  };

  function utils() {
    if (window.AnswerUtils) return window.AnswerUtils;
    return {
      isBonus: function (answer) { return answer === '送分' || answer === '*'; },
      isValid: function (answer) { return answer === '送分' || answer === '*' || /[A-D]/.test(String(answer || '')); },
      isCorrect: function (chosen, answer) {
        if (answer === '送分' || answer === '*') return true;
        return String(answer || '').match(/[A-D]/g).indexOf(chosen) !== -1;
      }
    };
  }

  function prepareQuiz(opts) {
    opts = opts || {};
    var filters = {
      cat: opts.cat || '',
      yr: opts.yr ? parseInt(opts.yr, 10) : null,
      sub: opts.sub || '',
      type: 'choice',
      ans: ''
    };
    var pool = SearchEngine.search('', filters, 99999).filter(function (question) {
      return question.optA && question.optB && question.optC && question.optD && utils().isValid(question.ans);
    });
    var count = Math.min(opts.count || 20, pool.length);
    var shuffled = pool.slice();
    if (opts.random !== false) {
      for (var i = shuffled.length - 1; i > 0; i--) {
        var j = Math.floor(Math.random() * (i + 1));
        var tmp = shuffled[i]; shuffled[i] = shuffled[j]; shuffled[j] = tmp;
      }
    }
    state.questions = shuffled.slice(0, count);
    state.answers = {};
    state.marked = {};
    state.current = 0;
    state.started = false;
    state.finished = false;
    return { total: state.questions.length, poolSize: pool.length };
  }

  function startQuiz(minutes) {
    state.started = true;
    state.finished = false;
    state.totalSeconds = Math.max(0, Number(minutes) || 0) * 60;
    state.secondsLeft = state.totalSeconds;
    if (state.totalSeconds > 0) _startTimer();
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
      if (typeof window.onTick === 'function') window.onTick(state.secondsLeft, state.totalSeconds);
    }, 1000);
  }

  function answer(idx, letter) {
    if (state.finished || idx < 0 || idx >= state.questions.length) return;
    if (!/^[A-D]$/.test(String(letter || '').toUpperCase())) return;
    state.answers[idx] = String(letter).toUpperCase();
  }

  function toggleMark(idx) {
    if (idx < 0 || idx >= state.questions.length) return false;
    if (state.marked[idx]) delete state.marked[idx];
    else state.marked[idx] = true;
    return !!state.marked[idx];
  }

  function goTo(idx) {
    if (idx >= 0 && idx < state.questions.length) state.current = idx;
  }
  function next() { goTo(state.current + 1); }
  function prev() { goTo(state.current - 1); }

  function finishQuiz() {
    if (state.timer) { clearInterval(state.timer); state.timer = null; }
    state.finished = true;
    var correct = 0, wrong = 0, unanswered = 0, bonus = 0;
    var wrongList = [];

    state.questions.forEach(function (question, index) {
      var chosen = state.answers[index];
      if (utils().isBonus(question.ans)) {
        bonus++;
        correct++;
      } else if (!chosen) {
        unanswered++;
        wrongList.push({ idx: index, question: question, chosen: null });
      } else if (utils().isCorrect(chosen, question.ans)) {
        correct++;
      } else {
        wrong++;
        wrongList.push({ idx: index, question: question, chosen: chosen });
      }
    });

    var elapsed = state.totalSeconds > 0 ? state.totalSeconds - state.secondsLeft : 0;
    return {
      correct: correct,
      wrong: wrong,
      unanswered: unanswered,
      bonus: bonus,
      total: state.questions.length,
      pct: state.questions.length ? Math.round(correct / state.questions.length * 100) : 0,
      elapsed: elapsed,
      wrongList: wrongList
    };
  }

  function getState() { return state; }
  function getQuestion(idx) { return state.questions[idx] || null; }
  function getCurrentQuestion() { return getQuestion(state.current); }
  function getAnswer(idx) { return state.answers[idx]; }
  function isMarked(idx) { return !!state.marked[idx]; }

  function saveHistory(result) {
    try {
      var history = JSON.parse(localStorage.getItem('exam-quiz-history-v2') || '[]');
      history.unshift({
        date: new Date().toISOString(),
        correct: result.correct,
        total: result.total,
        pct: result.pct,
        elapsed: result.elapsed,
        bonus: result.bonus || 0
      });
      localStorage.setItem('exam-quiz-history-v2', JSON.stringify(history.slice(0, 50)));
    } catch (error) {}
  }

  function getHistory() {
    try { return JSON.parse(localStorage.getItem('exam-quiz-history-v2') || '[]'); }
    catch (error) { return []; }
  }

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
    getHistory: getHistory
  };
})(window);
