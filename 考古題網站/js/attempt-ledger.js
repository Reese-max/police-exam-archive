/* === attempt-ledger.js — local-first per-question learning state === */
/*
 * The ledger stores facts (what happened for a question). Review state and
 * queue order are derived from those facts so a dataset refresh never has to
 * guess what an old aggregate score meant.
 */
(function (window) {
  'use strict';

  var LEDGER_KEY = 'exam-question-attempt-ledger';
  var SETTINGS_KEY = 'exam-review-settings';
  var SCHEMA_VERSION = 1;
  var DEFAULT_DATASET_VERSION = 'search-index-v1';
  var DAY_MS = 24 * 60 * 60 * 1000;
  var DEFAULT_SETTINGS = {
    deadlineEnabled: false,
    enabled: false,
    targetExamDate: '',
    dailyQuestionLimit: 20,
    dailyMinutes: 40,
  };

  function clone(value) {
    return JSON.parse(JSON.stringify(value));
  }

  function readJson(key, fallback) {
    try {
      var raw = window.localStorage.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) {
      return fallback;
    }
  }

  function writeJson(key, value) {
    window.localStorage.setItem(key, JSON.stringify(value));
    return true;
  }

  function text(value) {
    return value === null || value === undefined ? '' : String(value);
  }

  function first(value, fallback) {
    return value === undefined || value === null || value === '' ? fallback : value;
  }

  function locatorFor(question) {
    question = question || {};
    var locator = question.sourceLocator || question.locator || {};
    return {
      cat: text(first(locator.cat, first(question.cat, first(question.category, '')))),
      year: text(first(locator.year, first(locator.yr, first(question.yr, question.year || '')))),
      subject: text(first(locator.subject, first(locator.sub, first(question.sub, question.subject || '')))),
      no: text(first(locator.no, first(locator.number, first(question.no, question.number || '')))),
    };
  }

  function questionId(question) {
    question = question || {};
    if (question.questionId) return text(question.questionId);
    var locator = locatorFor(question);
    return [locator.cat, locator.year, locator.subject, locator.no].join('|');
  }

  function hashString(value) {
    var hash = 2166136261;
    for (var i = 0; i < value.length; i++) {
      hash ^= value.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return ('00000000' + (hash >>> 0).toString(16)).slice(-8);
  }

  function questionHash(question) {
    question = question || {};
    if (question.sourceHash || question.contentHash) return text(question.sourceHash || question.contentHash);
    var options = question.options || question.opts || [question.optA, question.optB, question.optC, question.optD];
    if (!Array.isArray(options)) options = [];
    var material = [
      questionId(question),
      text(first(question.stem, first(question.question, ''))),
      options.map(text).join('\u001f'),
      text(first(question.ans, question.answer || '')),
    ].join('\u001e');
    return 'fnv1a-' + hashString(material);
  }

  function datasetVersionFor(question, explicitVersion) {
    question = question || {};
    return text(first(explicitVersion, first(question.datasetVersion, first(question.datasetHash, DEFAULT_DATASET_VERSION))));
  }

  function answerOutcome(value) {
    if (value === 'correct' || value === 'wrong' || value === 'unanswered') return value;
    return 'unanswered';
  }

  function createEvent(input, metadata) {
    var data = input || {};
    if (metadata) {
      data = Object.assign({}, metadata, { question: input });
    }
    var question = data.question || data;
    var outcome = answerOutcome(first(data.answerOutcome, data.outcome));
    var markedReview = data.markedReview === true || data.outcome === 'marked_review' || data.marked_review === true;
    var event = {
      questionId: questionId(question),
      sourceLocator: locatorFor(question),
      attemptedAt: text(first(data.attemptedAt, new Date().toISOString())),
      outcome: outcome,
      answerOutcome: outcome,
      markedReview: markedReview,
      chosenAnswer: data.chosenAnswer === undefined ? null : data.chosenAnswer,
      datasetVersion: datasetVersionFor(question, data.datasetVersion),
      datasetHash: datasetVersionFor(question, data.datasetVersion),
      questionHash: text(first(data.questionHash, questionHash(question))),
      quizMode: text(first(data.quizMode, 'official')),
      filters: clone(data.filters || {}),
    };
    if (Number.isFinite(data.elapsedMs) && data.elapsedMs >= 0) event.elapsedMs = data.elapsedMs;
    return event;
  }

  function normaliseEvent(event) {
    if (!event || !event.questionId) return null;
    var out = clone(event);
    var wasMarkedReview = out.outcome === 'marked_review' || out.marked_review === true;
    out.questionId = text(out.questionId);
    out.attemptedAt = text(first(out.attemptedAt, new Date(0).toISOString()));
    if (!Number.isFinite(new Date(out.attemptedAt).getTime())) out.attemptedAt = new Date(0).toISOString();
    out.answerOutcome = answerOutcome(first(out.answerOutcome, out.outcome));
    out.outcome = out.answerOutcome;
    out.markedReview = out.markedReview === true || wasMarkedReview;
    if (!Object.prototype.hasOwnProperty.call(out, 'chosenAnswer')) out.chosenAnswer = null;
    out.datasetVersion = text(first(out.datasetVersion, first(out.datasetHash, DEFAULT_DATASET_VERSION)));
    out.datasetHash = out.datasetVersion;
    out.questionHash = text(out.questionHash || '');
    out.quizMode = text(first(out.quizMode, 'official'));
    out.filters = out.filters && typeof out.filters === 'object' ? out.filters : {};
    return out;
  }

  function getLedger() {
    var saved = readJson(LEDGER_KEY, []);
    if (!Array.isArray(saved)) return [];
    return saved.map(normaliseEvent).filter(Boolean);
  }

  function saveLedger(events) {
    return writeJson(LEDGER_KEY, events.map(normaliseEvent).filter(Boolean));
  }

  function replace(events) {
    var normalised = (events || []).map(normaliseEvent).filter(Boolean);
    saveLedger(normalised);
    return clone(normalised);
  }

  function append(events) {
    var current = getLedger();
    var incoming = (Array.isArray(events) ? events : [events]).map(normaliseEvent).filter(Boolean);
    current = current.concat(incoming);
    saveLedger(current);
    return clone(incoming);
  }

  function recordAttempt(input) {
    return append(createEvent(input));
  }

  function recordQuiz(config) {
    config = config || {};
    var questions = config.questions || [];
    var answers = config.answers || [];
    var marked = config.marked || [];
    var at = config.attemptedAt || new Date().toISOString();
    var events = questions.map(function (question, index) {
      var chosen = answers[index];
      var answerLetter = chosen === null || chosen === undefined ? null : (typeof chosen === 'number' ? 'ABCD'[chosen] : chosen);
      var correctAnswer = text(first(question.ans, question.answer || ''));
      return createEvent({
        question: question,
        attemptedAt: at,
        answerOutcome: answerLetter === null ? 'unanswered' : (answerLetter === correctAnswer ? 'correct' : 'wrong'),
        chosenAnswer: answerLetter,
        markedReview: marked[index] === true,
        elapsedMs: config.elapsedMsByQuestion && config.elapsedMsByQuestion[index],
        quizMode: config.quizMode || 'official',
        filters: config.filters || {},
      });
    });
    return append(events);
  }

  function getSettings() {
    var saved = readJson(SETTINGS_KEY, {});
    if (!saved || typeof saved !== 'object') saved = {};
    var settings = Object.assign({}, DEFAULT_SETTINGS, saved);
    settings.deadlineEnabled = saved.deadlineEnabled === true || saved.enabled === true;
    settings.enabled = settings.deadlineEnabled;
    settings.dailyQuestionLimit = Math.max(1, Math.floor(Number(settings.dailyQuestionLimit) || DEFAULT_SETTINGS.dailyQuestionLimit));
    settings.dailyMinutes = Math.max(0, Math.floor(Number.isFinite(Number(settings.dailyMinutes)) ? Number(settings.dailyMinutes) : DEFAULT_SETTINGS.dailyMinutes));
    settings.targetExamDate = /^\d{4}-\d{2}-\d{2}$/.test(text(settings.targetExamDate)) ? settings.targetExamDate : '';
    return settings;
  }

  function saveSettings(patch) {
    patch = patch || {};
    var current = getSettings();
    var next = Object.assign({}, current, patch);
    if (Object.prototype.hasOwnProperty.call(patch, 'enabled') && !Object.prototype.hasOwnProperty.call(patch, 'deadlineEnabled')) {
      next.deadlineEnabled = patch.enabled === true;
    }
    next.deadlineEnabled = next.deadlineEnabled === true;
    next.enabled = next.deadlineEnabled;
    next.dailyQuestionLimit = Math.max(1, Math.floor(Number(next.dailyQuestionLimit) || DEFAULT_SETTINGS.dailyQuestionLimit));
    next.dailyMinutes = Math.max(0, Math.floor(Number.isFinite(Number(next.dailyMinutes)) ? Number(next.dailyMinutes) : DEFAULT_SETTINGS.dailyMinutes));
    next.targetExamDate = /^\d{4}-\d{2}-\d{2}$/.test(text(next.targetExamDate)) ? next.targetExamDate : '';
    writeJson(SETTINGS_KEY, next);
    return clone(next);
  }

  function parseNow(value) {
    var parsed = value instanceof Date ? value.getTime() : new Date(value || Date.now()).getTime();
    return Number.isFinite(parsed) ? parsed : Date.now();
  }

  function targetDateMs(value) {
    if (!/^\d{4}-\d{2}-\d{2}$/.test(text(value))) return null;
    var parsed = new Date(text(value) + 'T23:59:59.999');
    return Number.isFinite(parsed.getTime()) ? parsed.getTime() : null;
  }

  function stateFor(question, events, options) {
    options = options || {};
    var nowMs = parseNow(options.now);
    var id = questionId(question);
    var matching = events.filter(function (event) { return event.questionId === id; }).sort(function (a, b) {
      return new Date(a.attemptedAt).getTime() - new Date(b.attemptedAt).getTime();
    });
    var currentHash = questionHash(question);
    var currentVersion = datasetVersionFor(question);
    var compatible = matching.filter(function (event) {
      // Build versions record provenance; compatibility is question-specific.
      return event.questionHash && event.questionHash === currentHash;
    });
    var latestFact = matching.length ? matching[matching.length - 1] : null;
    var sourceCompat = !latestFact || latestFact.questionHash === currentHash ? 'current' : 'stale';
    if (latestFact && !latestFact.questionHash) sourceCompat = 'review_required';
    var usable = sourceCompat === 'current' ? compatible : [];
    var latest = usable.length ? usable[usable.length - 1] : null;
    var wrongCount = usable.filter(function (event) { return event.answerOutcome === 'wrong'; }).length;
    var unansweredCount = usable.filter(function (event) { return event.answerOutcome === 'unanswered'; }).length;
    var correctStreak = 0;
    var consecutiveWrongCount = 0;
    for (var i = usable.length - 1; i >= 0; i--) {
      if (usable[i].answerOutcome === 'correct') correctStreak++;
      else break;
    }
    for (var j = usable.length - 1; j >= 0; j--) {
      if (usable[j].answerOutcome === 'wrong') consecutiveWrongCount++;
      else break;
    }
    var lastSeen = latest ? latest.attemptedAt : null;
    var lastWrong = null;
    usable.forEach(function (event) {
      if (event.answerOutcome === 'wrong') lastWrong = event.attemptedAt;
    });
    var dueAt = null;
    if (latest && sourceCompat === 'current') {
      var latestMs = parseNow(latest.attemptedAt);
      var intervalDays;
      if (latest.markedReview) intervalDays = 0;
      else if (latest.answerOutcome === 'wrong' || latest.answerOutcome === 'unanswered') intervalDays = 1;
      else intervalDays = [1, 3, 7, 14, 21][Math.min(correctStreak, 5) - 1] || 21;
      dueAt = new Date(latestMs + intervalDays * DAY_MS).toISOString();
    }

    var reasonCodes = [];
    if (sourceCompat !== 'current') reasonCodes.push('資料集版本不相容');
    if (latest && sourceCompat === 'current') {
      if (latest.answerOutcome === 'wrong') reasonCodes.push('上次答錯');
      if (latest.answerOutcome === 'unanswered') reasonCodes.push('上次未答');
      if (consecutiveWrongCount >= 2) reasonCodes.push('連續 ' + consecutiveWrongCount + ' 次答錯');
      if (latest.markedReview) reasonCodes.push('標記回顧');
      if (dueAt && parseNow(dueAt) <= nowMs) reasonCodes.push('到期複習');
      if (lastSeen && nowMs - parseNow(lastSeen) >= 21 * DAY_MS) reasonCodes.push('21 天未複習');
    }
    if (!matching.length) reasonCodes.push('探索新題');

    var targetMs = options.targetDateMs;
    if (targetMs === undefined) {
      var settings = Object.assign({}, getSettings(), options.settings || {});
      targetMs = settings.deadlineEnabled || settings.enabled ? targetDateMs(settings.targetExamDate) : null;
    }
    if (targetMs && dueAt && parseNow(dueAt) > targetMs) {
      dueAt = new Date(targetMs).toISOString();
      reasonCodes.push('考試日前完成');
    }
    return {
      questionId: id,
      attempts: matching.length,
      compatibleAttempts: usable.length,
      wrongCount: wrongCount,
      unansweredCount: unansweredCount,
      correctStreak: correctStreak,
      consecutiveWrongCount: consecutiveWrongCount,
      lastSeen: lastSeen,
      lastWrong: lastWrong,
      dueAt: dueAt,
      reasonCodes: reasonCodes,
      sourceCompat: sourceCompat,
      datasetVersion: currentVersion,
      questionHash: currentHash,
      subject: locatorFor(question).subject,
      group: JSON.stringify([locatorFor(question).cat, locatorFor(question).subject]),
    };
  }

  function candidateFor(question, state, nowMs) {
    var latestWrong = state.reasonCodes.indexOf('上次答錯') >= 0;
    var latestUnanswered = state.reasonCodes.indexOf('上次未答') >= 0;
    var marked = state.reasonCodes.indexOf('標記回顧') >= 0;
    var due = state.dueAt && parseNow(state.dueAt) <= nowMs;
    var stale = state.sourceCompat !== 'current';
    var coverage = state.reasonCodes.indexOf('本科目近期覆蓋不足') >= 0;
    var explore = state.reasonCodes.indexOf('探索新題') >= 0;
    var priority = 0;
    var category = 'recent';
    if (stale) { priority = 350; category = 'review_required'; }
    if (due) { priority = Math.max(priority, 300); category = 'due'; }
    if (latestUnanswered) { priority = Math.max(priority, 390); category = 'urgent'; }
    if (latestWrong) { priority = Math.max(priority, 400); category = 'urgent'; }
    if (marked) { priority = Math.max(priority, 420); category = 'urgent'; }
    if (coverage && priority < 200) { priority = 200; category = 'coverage'; }
    if (explore && priority < 100) { priority = 100; category = 'exploration'; }
    return {
      questionId: state.questionId,
      question: question,
      reasonCodes: state.reasonCodes.slice(),
      reason: state.reasonCodes[0] || '今日複習',
      dueAt: state.dueAt,
      sourceCompat: state.sourceCompat,
      reviewState: state,
      priority: priority,
      category: category,
      subject: state.subject || text(question.sub || question.subject || question.cat),
      group: state.group,
    };
  }

  function buildQueue(questions, options) {
    options = options || {};
    var settings = Object.assign({}, getSettings(), options.settings || {});
    settings.deadlineEnabled = settings.deadlineEnabled === true || settings.enabled === true;
    var nowMs = parseNow(options.now);
    var targetMs = settings.deadlineEnabled ? targetDateMs(settings.targetExamDate) : null;
    var events = getLedger();
    var states = (questions || []).map(function (question) { return stateFor(question, events, { now: nowMs, targetDateMs: targetMs }); });
    var byId = {};
    states.forEach(function (state) { byId[state.questionId] = state; });
    var subjectCounts = {};
    states.forEach(function (state) {
      var subject = state.group;
      if (!subjectCounts[subject]) subjectCounts[subject] = { lastSeen: -Infinity, candidate: null };
      if (state.lastSeen) subjectCounts[subject].lastSeen = Math.max(subjectCounts[subject].lastSeen, parseNow(state.lastSeen));
    });
    states.forEach(function (state) {
      if (nowMs - subjectCounts[state.group].lastSeen >= 21 * DAY_MS) state.reasonCodes.push('本科目近期覆蓋不足');
    });
    var candidates = (questions || []).map(function (question) {
      return candidateFor(question, byId[questionId(question)], nowMs);
    }).filter(function (candidate) { return candidate.priority > 0; });
    candidates.sort(function (a, b) {
      return b.priority - a.priority || a.questionId.localeCompare(b.questionId);
    });
    candidates.forEach(function (candidate) {
      if (!subjectCounts[candidate.group].candidate) subjectCounts[candidate.group].candidate = candidate;
    });

    var limit = Math.max(1, Math.floor(Number(options.limit || settings.dailyQuestionLimit) || 1));
    var selected = [];
    var selectedIds = {};
    // ponytail: one-question sessions rotate coverage; larger sessions reserve at least half for priority.
    var coverageSlots = Math.max(1, Math.floor(limit / 2));
    var subjects = Object.keys(subjectCounts).filter(function (subject) { return subjectCounts[subject].candidate; }).sort(function (a, b) {
      var left = subjectCounts[a], right = subjectCounts[b];
      return left.lastSeen - right.lastSeen || right.candidate.priority - left.candidate.priority || a.localeCompare(b);
    });
    subjects.forEach(function (subject) {
      if (selected.length >= coverageSlots) return;
      var candidate = subjectCounts[subject].candidate;
      if (candidate && !selectedIds[candidate.questionId]) {
        selected.push(candidate);
        selectedIds[candidate.questionId] = true;
      }
    });
    candidates.forEach(function (candidate) {
      if (selected.length >= limit || selectedIds[candidate.questionId]) return;
      selected.push(candidate);
      selectedIds[candidate.questionId] = true;
    });
    selected.sort(function (a, b) {
      return b.priority - a.priority || a.questionId.localeCompare(b.questionId);
    });

    var weak = candidates.filter(function (candidate) {
      return candidate.category === 'urgent' || candidate.category === 'due' || candidate.category === 'review_required';
    }).length;
    var capacity = null;
    var overload = false;
    var backlogCount = 0;
    if (settings.deadlineEnabled && targetMs) {
      var availableDays = Math.max(0, Math.ceil((targetMs - nowMs) / DAY_MS));
      capacity = availableDays * settings.dailyQuestionLimit;
      overload = weak > capacity;
      backlogCount = Math.max(0, weak - capacity);
    }
    return {
      items: selected,
      states: states,
      overload: overload,
      backlogCount: backlogCount,
      capacity: capacity,
      weakCount: weak,
      deadline: settings.deadlineEnabled && !!targetMs,
      settings: clone(settings),
      generatedAt: new Date(nowMs).toISOString(),
    };
  }

  function exportData() {
    return JSON.stringify({
      schemaVersion: SCHEMA_VERSION,
      exportedAt: new Date().toISOString(),
      attemptLedger: getLedger(),
      reviewSettings: getSettings(),
    });
  }

  function importData(payload) {
    var data = typeof payload === 'string' ? JSON.parse(payload) : payload;
    if (!data || !Array.isArray(data.attemptLedger)) throw new Error('匯入檔缺少 attemptLedger');
    if (data.schemaVersion !== SCHEMA_VERSION) throw new Error('不支援的學習資料版本');
    data.attemptLedger.forEach(function (event) {
      if (!event || typeof event.questionId !== 'string' || !event.questionId ||
          !event.sourceLocator || ['cat', 'year', 'subject', 'no'].some(function (key) { return typeof event.sourceLocator[key] !== 'string' || !event.sourceLocator[key]; }) ||
          typeof event.attemptedAt !== 'string' || !Number.isFinite(Date.parse(event.attemptedAt)) ||
          ['correct', 'wrong', 'unanswered'].indexOf(event.answerOutcome) < 0 ||
          event.outcome !== event.answerOutcome || typeof event.markedReview !== 'boolean' ||
          !(event.chosenAnswer === null || (typeof event.chosenAnswer === 'string' && /^[ABCD]$/.test(event.chosenAnswer))) ||
          typeof event.datasetVersion !== 'string' || !event.datasetVersion ||
          typeof event.questionHash !== 'string' || !event.questionHash ||
          typeof event.quizMode !== 'string' || !event.filters || typeof event.filters !== 'object' || Array.isArray(event.filters) ||
          (event.elapsedMs !== undefined && (!Number.isFinite(event.elapsedMs) || event.elapsedMs < 0))) {
        throw new Error('匯入檔含無效作答紀錄');
      }
    });
    var settings = data.reviewSettings;
    if (settings !== undefined && (!settings || typeof settings !== 'object' || Array.isArray(settings) ||
        ['deadlineEnabled', 'enabled'].some(function (key) { return settings[key] !== undefined && typeof settings[key] !== 'boolean'; }) ||
        ['dailyQuestionLimit', 'dailyMinutes'].some(function (key) { return settings[key] !== undefined && (!Number.isInteger(settings[key]) || settings[key] < (key === 'dailyMinutes' ? 0 : 1)); }) ||
        (settings.targetExamDate !== undefined && settings.targetExamDate !== '' &&
          (!targetDateMs(settings.targetExamDate) || new Date(settings.targetExamDate + 'T00:00:00Z').toISOString().slice(0, 10) !== settings.targetExamDate)))) {
      throw new Error('匯入檔含無效複習設定');
    }
    var imported = data.attemptLedger.map(normaliseEvent);
    var previousLedger = window.localStorage.getItem(LEDGER_KEY);
    replace(imported);
    try {
      if (settings) saveSettings(settings);
    } catch (e) {
      if (previousLedger === null) window.localStorage.removeItem(LEDGER_KEY);
      else window.localStorage.setItem(LEDGER_KEY, previousLedger);
      throw e;
    }
    return { attempts: imported.length, settings: getSettings() };
  }

  function clearLearnerData() {
    try {
      window.localStorage.removeItem(LEDGER_KEY);
      window.localStorage.removeItem(SETTINGS_KEY);
      window.localStorage.removeItem('exam-quiz-history');
      return true;
    } catch (e) {
      return false;
    }
  }

  window.AttemptLedger = {
    schemaVersion: SCHEMA_VERSION,
    questionId: questionId,
    questionHash: questionHash,
    createEvent: createEvent,
    getLedger: getLedger,
    replace: replace,
    append: append,
    recordAttempt: recordAttempt,
    recordQuiz: recordQuiz,
    getSettings: getSettings,
    saveSettings: saveSettings,
    getReviewState: function (question, options) { return stateFor(question, getLedger(), options || {}); },
    buildQueue: buildQueue,
    exportData: exportData,
    importData: importData,
    clearLearnerData: clearLearnerData,
  };
})(window);
