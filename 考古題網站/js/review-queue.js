/* === review-queue.js — 本機逐題作答帳本與考前複習佇列 === */
(function (window) {
  'use strict';

  var SCHEMA_VERSION = 1;
  var LEDGER_KEY = 'exam-attempt-ledger-v1';
  var SETTINGS_KEY = 'exam-review-settings-v1';
  var HISTORY_KEY = 'exam-quiz-history';
  var MINUTES_PER_QUESTION = 2;
  var UNSEEN_CANDIDATES_PER_SUBJECT = 4;
  var MAX_ATTEMPTS_PER_QUESTION = 30;
  var VALID_OUTCOMES = { correct: true, wrong: true, unanswered: true };
  var DEFAULT_SETTINGS = {
    deadline_enabled: false,
    target_date: null,
    daily_question_limit: 20,
    daily_minutes: null,
  };
  var REASON_LABELS = {
    marked_review: '標記回顧',
    repeated_wrong: '連續答錯',
    last_wrong: '上次答錯',
    unanswered: '上次未答',
    due: '已到期複習',
    coverage_gap: '本科目近期覆蓋不足',
    unseen: '尚未作答過',
    dataset_changed: '資料版本變更，需重新確認',
  };

  function storageOrDefault(storage) {
    if (storage) return storage;
    try { return window.localStorage; } catch (e) { return null; }
  }

  function readJson(storage, key, fallback) {
    var target = storageOrDefault(storage);
    if (!target) return fallback;
    try {
      var raw = target.getItem(key);
      return raw ? JSON.parse(raw) : fallback;
    } catch (e) { return fallback; }
  }

  function writeJson(storage, key, value) {
    var target = storageOrDefault(storage);
    if (!target) return false;
    try {
      target.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) { return false; }
  }

  function emptyLedger() {
    return { schema_version: SCHEMA_VERSION, attempts: [] };
  }

  function blockedLedger(message) {
    var ledger = emptyLedger();
    ledger.write_blocked = true;
    ledger.storage_error = message;
    return ledger;
  }

  function validAttempt(item) {
    if (!item || typeof item !== 'object' || Array.isArray(item)
        || typeof item.question_id !== 'string' || !item.question_id
        || VALID_OUTCOMES[item.outcome] !== true
        || typeof item.source_hash !== 'string' || !item.source_hash
        || typeof item.attempted_at !== 'string' || !parseDate(item.attempted_at)
        || !item.source_locator || typeof item.source_locator !== 'object' || Array.isArray(item.source_locator)
        || typeof item.source_locator.number !== 'string' || !item.source_locator.number) return false;
    if (item.marked_review !== undefined && typeof item.marked_review !== 'boolean') return false;
    if (item.chosen_answer !== undefined && item.chosen_answer !== null
        && (typeof item.chosen_answer !== 'string' || !/^[ABCD]$/.test(item.chosen_answer))) return false;
    var index = item.source_locator.index;
    if (index != null && (!Number.isInteger(index) || index < 0)) return false;
    if (item.elapsed_seconds !== undefined && (!Number.isInteger(item.elapsed_seconds) || item.elapsed_seconds < 0)) return false;
    if (item.outcome_codes !== undefined && (!Array.isArray(item.outcome_codes)
        || item.outcome_codes.indexOf(item.outcome) < 0
        || !item.outcome_codes.every(function (code) { return VALID_OUTCOMES[code] === true || code === 'marked_review'; })
        || (item.marked_review !== undefined && (item.outcome_codes.indexOf('marked_review') >= 0) !== item.marked_review))) return false;
    return true;
  }

  function getLedger(storage) {
    var target = storageOrDefault(storage);
    if (!target) return blockedLedger('本機儲存空間無法使用，已停止寫入逐題作答紀錄。');
    var raw;
    try { raw = target.getItem(LEDGER_KEY); }
    catch (e) { return blockedLedger('無法讀取原逐題作答紀錄，已停止寫入，原資料未變更。請保留原資料並恢復本機儲存後重試。'); }
    if (raw == null || raw === '') return emptyLedger();
    var ledger;
    try { ledger = JSON.parse(raw); } catch (e) { ledger = null; }
    if (ledger && ledger.schema_version === SCHEMA_VERSION && Array.isArray(ledger.attempts)
        && ledger.attempts.every(validAttempt)) {
      return { schema_version: SCHEMA_VERSION, attempts: ledger.attempts.slice() };
    }
    // A failed duplicate can coexist with a successful smaller replacement
    // near the quota. Allow replacement only after an exact quarantine readback.
    try {
      if (target.getItem(LEDGER_KEY + '.corrupt') !== raw) target.setItem(LEDGER_KEY + '.corrupt', raw);
      if (target.getItem(LEDGER_KEY + '.corrupt') === raw) return emptyLedger();
    } catch (e) {}
    return blockedLedger('原逐題作答紀錄格式異常且無法隔離保存，已停止寫入、匯入與匯出，原資料未變更。請先保留原資料並釋放儲存空間後重試。');
  }

  // Keep only the newest events per question so a long-lived ledger cannot
  // grow past the localStorage quota and silently stop persisting.
  function compactAttempts(attempts) {
    var counts = Object.create(null);
    var kept = [];
    for (var i = attempts.length - 1; i >= 0; i--) {
      var id = attempts[i] && attempts[i].question_id;
      counts[id] = (counts[id] || 0) + 1;
      if (counts[id] <= MAX_ATTEMPTS_PER_QUESTION) kept.unshift(attempts[i]);
    }
    return kept;
  }

  function saveLedger(ledger, storage) {
    if (ledger.write_blocked || getLedger(storage).write_blocked) return false;
    return writeJson(storage, LEDGER_KEY, {
      schema_version: SCHEMA_VERSION,
      attempts: compactAttempts(Array.isArray(ledger.attempts) ? ledger.attempts : []),
    });
  }

  function normalizeSettings(input) {
    var value = input || {};
    var limit = Number(value.daily_question_limit != null ? value.daily_question_limit : value.dailyLimit);
    var minutes = value.daily_minutes != null ? value.daily_minutes : value.dailyMinutes;
    minutes = minutes === '' || minutes == null ? null : Number(minutes);
    var target = value.target_date || value.targetDate || null;
    // Validate against the real calendar, not just the regex: `Date` parsing
    // rolls 2026-02-31 into March, which would otherwise leave deadline mode
    // enabled with a deadline that can never resolve.
    if (target && (!/^\d{4}-\d{2}-\d{2}$/.test(target) || !deadlineEnd(target))) {
      target = null;
    }
    return {
      deadline_enabled: !!(value.deadline_enabled != null ? value.deadline_enabled : value.deadlineEnabled),
      target_date: target || null,
      daily_question_limit: Number.isFinite(limit) && limit > 0 ? Math.min(Math.floor(limit), 200) : DEFAULT_SETTINGS.daily_question_limit,
      daily_minutes: Number.isFinite(minutes) && minutes > 0 ? Math.min(Math.floor(minutes), 1440) : null,
    };
  }

  function getSettings(storage) {
    return normalizeSettings(readJson(storage, SETTINGS_KEY, DEFAULT_SETTINGS));
  }

  function saveSettings(settings, storage) {
    var normalized = normalizeSettings(settings);
    if (!writeJson(storage, SETTINGS_KEY, normalized)) throw new Error('排程設定儲存失敗：本機儲存空間不足或無法寫入，原設定未變更');
    return normalized;
  }

  function questionSource(question) {
    return question && question.source ? question.source : (question || {});
  }

  function stableText(value) {
    return value == null ? '' : String(value);
  }

  // A small deterministic content fingerprint is enough to detect dataset drift;
  // it does not pretend to be a cryptographic identity.
  function contentHash(question) {
    var q = questionSource(question);
    var text = [q.stem, q.optA, q.optB, q.optC, q.optD, q.ans].map(stableText).join('\u001f');
    var hash = 2166136261;
    for (var i = 0; i < text.length; i++) {
      hash ^= text.charCodeAt(i);
      hash = Math.imul(hash, 16777619);
    }
    return 'fnv1a-' + (hash >>> 0).toString(16).padStart(8, '0');
  }

  function questionId(question) {
    var q = questionSource(question);
    return [stableText(q.cat || q.category), stableText(q.yr || q.year), stableText(q.sub || q.subject), stableText(q.no || q.number)].join('|');
  }

  function questionIdentity(question, datasetVersion) {
    var q = questionSource(question);
    var category = stableText(q.cat || q.category);
    var year = stableText(q.yr || q.year);
    var subject = stableText(q.sub || q.subject);
    var number = stableText(q.no || q.number);
    return {
      question_id: questionId(q),
      source_locator: {
        category: category,
        year: year,
        subject: subject,
        number: number,
        // Search-index row position disambiguates the rare locator collisions
        // (same 類科/年份/科目/題號 appearing twice in one dataset build).
        index: q.idx != null ? q.idx : null,
      },
      source_hash: contentHash(q),
      dataset_version: stableText(datasetVersion || q.dataset_version || 'unknown'),
    };
  }

  function answerLetter(answer) {
    if (answer == null || answer === '') return null;
    if (typeof answer === 'number') return 'ABCD'[answer] || null;
    var text = String(answer).toUpperCase();
    return text.length === 1 && 'ABCD'.indexOf(text) >= 0 ? text : null;
  }

  function recordQuizAttempt(questions, answers, marked, options, storage) {
    var opts = options || {};
    var ledger = getLedger(storage);
    if (ledger.write_blocked) {
      ledger.persisted = false;
      return ledger;
    }
    var attemptedAt = isoDate(opts.attemptedAt) || new Date().toISOString();
    var datasetVersion = opts.datasetVersion || 'unknown';
    var mode = opts.quizMode || 'simulated';
    var filters = opts.filters || {};
    var events = (questions || []).map(function (question, index) {
      var q = questionSource(question);
      var identity = questionIdentity(q, datasetVersion);
      var chosen = answerLetter(answers && answers[index]);
      // No valid answer key means the event is recorded but cannot be
      // graded — count it as unanswered rather than inflating wrong_count.
      var answerKey = answerLetter(q.ans);
      var outcome = !chosen || !answerKey ? 'unanswered' : chosen === answerKey ? 'correct' : 'wrong';
      var event = {
        attempt_id: attemptedAt + ':' + identity.question_id + ':' + index,
        attempted_at: attemptedAt,
        question_id: identity.question_id,
        source_locator: identity.source_locator,
        source_hash: identity.source_hash,
        dataset_version: identity.dataset_version,
        outcome: outcome,
        outcome_codes: marked && marked[index] ? [outcome, 'marked_review'] : [outcome],
        chosen_answer: chosen,
        marked_review: !!(marked && marked[index]),
        quiz_mode: mode,
        filters: filters,
      };
      if (opts.questionElapsed && Number.isFinite(opts.questionElapsed[index])) {
        event.elapsed_seconds = Math.max(0, Math.floor(opts.questionElapsed[index]));
      }
      return event;
    });
    ledger.attempts = ledger.attempts.concat(events);
    ledger.persisted = saveLedger(ledger, storage);
    return ledger;
  }

  function saveQuizSummary(summary, storage) {
    var target = storageOrDefault(storage);
    if (!target) return false;
    var history = readJson(target, HISTORY_KEY, []);
    if (!Array.isArray(history)) history = [];
    history.unshift(summary);
    return writeJson(target, HISTORY_KEY, history.slice(0, 50));
  }

  function parseDate(value) {
    var date = value instanceof Date ? new Date(value.getTime()) : new Date(value);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function isoDate(value) {
    var date = parseDate(value);
    return date ? date.toISOString() : null;
  }

  function addDays(iso, days) {
    var date = parseDate(iso);
    if (!date) return null;
    date.setUTCDate(date.getUTCDate() + days);
    return date.toISOString();
  }

  // Code-point compare: localeCompare collations can differ between Node and
  // browsers, and the queue must replay identically in both.
  function compareText(a, b) {
    a = String(a); b = String(b);
    return a < b ? -1 : a > b ? 1 : 0;
  }

  function latestAttempt(attempts) {
    return attempts.reduce(function (latest, item) {
      if (!latest || String(item.attempted_at) >= String(latest.attempted_at)) return item;
      return latest;
    }, null);
  }

  function deriveReviewState(question, attempts, now, datasetVersion, locatorCount) {
    var identity = questionIdentity(question, datasetVersion);
    var all = (attempts || []).filter(function (item) { return item.question_id === identity.question_id; });
    // A locator unique in the current full bank survives positional inserts.
    // Ambiguous locators retain conservative row ownership; their siblings'
    // facts must not be silently applied to another question.
    var owned = all.filter(function (item) {
      var li = item.source_locator ? item.source_locator.index : null;
      var qi = identity.source_locator.index;
      return locatorCount === 1 || li == null || qi == null || li === qi;
    });
    // Compatibility keys on the content fingerprint, not the dataset version:
    // attempts against identical question content re-map across index rebuilds,
    // and re-attempting changed content lets the state recover instead of
    // pinning STALE forever. Old-version events stay in the ledger as facts.
    var compatible = owned.filter(function (item) {
      return item.source_hash === identity.source_hash;
    });
    var stale = owned.length > 0 && compatible.length === 0;
    var ordered = compatible.slice().sort(function (a, b) {
      return compareText(a.attempted_at, b.attempted_at);
    });
    var latest = latestAttempt(ordered);
    var wrongCount = ordered.filter(function (item) { return item.outcome === 'wrong'; }).length;
    var unansweredCount = ordered.filter(function (item) { return item.outcome === 'unanswered'; }).length;
    var correctStreak = 0;
    for (var i = ordered.length - 1; i >= 0 && ordered[i].outcome === 'correct'; i--) correctStreak++;
    var wrongStreak = 0;
    for (var j = ordered.length - 1; j >= 0 && ordered[j].outcome === 'wrong'; j--) wrongStreak++;
    var lastWrong = ordered.reduce(function (last, item) {
      return item.outcome === 'wrong' || item.outcome === 'unanswered' ? item.attempted_at : last;
    }, null);
    var dueAt = null;
    if (latest) {
      var interval = latest.outcome === 'correct'
        ? (correctStreak >= 3 ? 14 : correctStreak === 2 ? 7 : 3)
        : 1;
      dueAt = addDays(latest.attempted_at, interval);
    }

    var reasons = [];
    if (stale) reasons.push('dataset_changed');
    if (latest && latest.marked_review) reasons.push('marked_review');
    if (latest && latest.outcome === 'wrong') reasons.push(wrongStreak >= 2 ? 'repeated_wrong' : 'last_wrong');
    if (latest && latest.outcome === 'unanswered') reasons.push('unanswered');
    if (latest && dueAt && dueAt <= isoDate(now)) reasons.push('due');
    if (!latest && !stale) reasons.push('coverage_gap');

    return {
      status: stale ? 'STALE' : 'CURRENT',
      source_compatible: !stale,
      question_id: identity.question_id,
      source_locator: identity.source_locator,
      source_hash: identity.source_hash,
      dataset_version: identity.dataset_version,
      attempts: ordered.length,
      wrong_count: stale ? 0 : wrongCount,
      unanswered_count: stale ? 0 : unansweredCount,
      correct_streak: stale ? 0 : correctStreak,
      last_seen: latest ? latest.attempted_at : null,
      last_wrong: stale ? null : lastWrong,
      due_at: stale ? null : dueAt,
      marked_review: !!(latest && latest.marked_review),
      reason_codes: reasons,
    };
  }

  function deadlineEnd(targetDate) {
    // End of the target day in the user's local timezone — the audience is not
    // UTC, and anchoring to `T23:59:59Z` would spill scheduling into the
    // morning after the chosen date.
    var parts = targetDate && /^(\d{4})-(\d{2})-(\d{2})$/.exec(targetDate);
    if (!parts) return null;
    var end = new Date(+parts[1], +parts[2] - 1, +parts[3], 23, 59, 59, 999);
    // Local construction rolls impossible dates (e.g. Feb 31) into March —
    // reject them instead of silently scheduling past the chosen day.
    if (Number.isNaN(end.getTime()) || end.getDate() !== +parts[3]) return null;
    return end.toISOString();
  }

  function subjectKey(question) {
    var q = questionSource(question);
    return stableText(q.sub || q.subject) || stableText(q.cat || q.category);
  }

  function locatorSubject(locator) {
    return locator ? (stableText(locator.subject) || stableText(locator.category)) : '';
  }

  function roundRobin(items) {
    var groups = Object.create(null);
    items.slice().sort(function (a, b) {
      return compareText(a.question_id, b.question_id);
    }).forEach(function (item) {
      var key = subjectKey(item.question);
      if (!groups[key]) groups[key] = [];
      groups[key].push(item);
    });
    var keys = Object.keys(groups).sort();
    var output = [];
    var added = true;
    while (added) {
      added = false;
      keys.forEach(function (key) {
        if (groups[key].length) {
          output.push(groups[key].shift());
          added = true;
        }
      });
    }
    return output;
  }

  function buildReviewQueue(questions, ledger, settings, now, datasetVersion) {
    var current = isoDate(now || new Date().toISOString()) || new Date().toISOString();
    var normalized = normalizeSettings(settings);
    var sourceLedger = ledger && Array.isArray(ledger.attempts) ? ledger.attempts : [];
    var attemptsByQuestion = Object.create(null);
    var locatorCounts = Object.create(null);
    // Index current content per subject first: an attempt only counts as
    // covering a subject when its content fingerprint still maps to a live
    // question — a fully stale history must not hide the coverage gap.
    var currentHashes = Object.create(null);
    (questions || []).forEach(function (question) {
      var q = questionSource(question);
      var subject = subjectKey(q);
      if (!currentHashes[subject]) currentHashes[subject] = Object.create(null);
      var identity = questionIdentity(q, datasetVersion || q.dataset_version);
      locatorCounts[identity.question_id] = (locatorCounts[identity.question_id] || 0) + 1;
      currentHashes[subject][identity.source_hash] = true;
    });
    var coveredSubjects = Object.create(null);
    sourceLedger.forEach(function (attempt) {
      if (!attemptsByQuestion[attempt.question_id]) attemptsByQuestion[attempt.question_id] = [];
      attemptsByQuestion[attempt.question_id].push(attempt);
      var subject = locatorSubject(attempt.source_locator);
      if (subject && currentHashes[subject] && currentHashes[subject][attempt.source_hash]) {
        coveredSubjects[subject] = true;
      }
    });
    var unseenPerSubject = Object.create(null);
    var records = [];
    (questions || []).forEach(function (question) {
      var q = questionSource(question);
      var id = questionId(q);
      var questionAttempts = attemptsByQuestion[id];
      var state;
      if (!questionAttempts) {
        // Unseen questions: a bounded number per subject become exploration
        // candidates. A subject with no attempt history is a coverage gap;
        // one already covered still contributes a small trickle of new items.
        var subject = subjectKey(q);
        var gap = !coveredSubjects[subject];
        var code = gap ? 'coverage_gap' : 'unseen';
        var key = (gap ? 'gap|' : 'new|') + subject;
        if ((unseenPerSubject[key] || 0) >= UNSEEN_CANDIDATES_PER_SUBJECT) return;
        unseenPerSubject[key] = (unseenPerSubject[key] || 0) + 1;
        var identity = questionIdentity(q, datasetVersion || q.dataset_version);
        state = {
          status: 'CURRENT', source_compatible: true, question_id: identity.question_id,
          source_locator: identity.source_locator, source_hash: identity.source_hash,
          dataset_version: identity.dataset_version, attempts: 0, wrong_count: 0,
          unanswered_count: 0, correct_streak: 0, last_seen: null, last_wrong: null,
          due_at: null, marked_review: false, reason_codes: [code],
        };
      } else {
        state = deriveReviewState(q, questionAttempts, current, datasetVersion || q.dataset_version, locatorCounts[id]);
      }
      var reason;
      var priority;
      if (state.status === 'STALE') {
        reason = 'dataset_changed'; priority = 0;
      } else if (state.marked_review) {
        reason = 'marked_review'; priority = 1;
      } else if (state.reason_codes.indexOf('last_wrong') >= 0 || state.reason_codes.indexOf('repeated_wrong') >= 0 || state.reason_codes.indexOf('unanswered') >= 0) {
        reason = state.reason_codes.indexOf('repeated_wrong') >= 0 ? 'repeated_wrong' : state.reason_codes.indexOf('unanswered') >= 0 ? 'unanswered' : 'last_wrong';
        priority = 1;
      } else if (state.reason_codes.indexOf('due') >= 0) {
        reason = 'due'; priority = 2;
      } else if (!state.attempts) {
        reason = state.reason_codes[0] === 'unseen' ? 'unseen' : 'coverage_gap';
        priority = reason === 'unseen' ? 4 : 3;
      } else {
        return null;
      }
      var due = state.due_at || current;
      var end = normalized.deadline_enabled ? deadlineEnd(normalized.target_date) : null;
      var scheduled = end && due > end ? end : due;
      records.push({
        question: q,
        question_id: state.question_id,
        state: state,
        priority: priority,
        reason_code: reason,
        reason_label: REASON_LABELS[reason],
        due_at: state.due_at,
        scheduled_due_at: scheduled,
      });
    });

    var capacity = normalized.daily_question_limit;
    if (normalized.daily_minutes) capacity = Math.min(capacity, Math.max(0, Math.floor(normalized.daily_minutes / MINUTES_PER_QUESTION)));
    var staleItems = roundRobin(records.filter(function (item) { return item.priority === 0; }));
    var strong = roundRobin(records.filter(function (item) { return item.priority === 1; }));
    var dueCandidates = roundRobin(records.filter(function (item) { return item.priority === 2; }));
    var coverageCandidates = roundRobin(records.filter(function (item) { return item.priority === 3; }));
    var unseenCandidates = roundRobin(records.filter(function (item) { return item.priority === 4; }));
    var exploration = coverageCandidates.concat(unseenCandidates);
    var selected = [];
    var selectedRows = Object.create(null);
    function add(item) {
      // Dedupe by row, not question_id: locator collisions legitimately put
      // two distinct rows under one id, and each deserves its own slot.
      var rowKey = item.question && item.question.idx != null
        ? 'idx:' + item.question.idx
        : 'qid:' + item.question_id + ':' + item.state.source_hash;
      if (!item || selectedRows[rowKey] || selected.length >= capacity) return;
      selectedRows[rowKey] = true;
      selected.push(item);
    }
    // Fill order honors the declared tiers: stale items need re-confirmation
    // first, then a bounded share of weak items, due reviews, and a small
    // exploration slice; leftovers fall back to the remaining queue.
    var explorationQuota = Math.min(exploration.length, Math.max(1, Math.floor(capacity * 0.2)));
    staleItems.forEach(add);
    // The exploration floor only applies when the queue can actually share:
    // at capacity 1 the single slot goes to the highest-priority item.
    var explorationReserve = exploration.length && capacity >= 2 && selected.length < capacity
      ? Math.min(explorationQuota, capacity - selected.length) : 0;
    var strongQuota = Math.min(strong.length, Math.max(0, Math.min(
      Math.ceil(capacity * 0.6), capacity - selected.length - explorationReserve)));
    strong.slice(0, strongQuota).forEach(add);
    dueCandidates.slice(0, Math.max(0, capacity - selected.length - explorationReserve)).forEach(add);
    exploration.slice(0, explorationQuota).forEach(add);
    strong.slice(strongQuota).forEach(add);
    dueCandidates.forEach(add);
    exploration.slice(explorationQuota).forEach(add);

    var weakCount = records.filter(function (item) { return item.priority <= 2; }).length;
    var hasDeadline = normalized.deadline_enabled && !!normalized.target_date;
    var availableCapacity = capacity;
    var daysRemaining = null;
    if (hasDeadline) {
      var today = parseDate(current);
      var target = parseDate(deadlineEnd(normalized.target_date));
      daysRemaining = today && target ? Math.max(0, Math.floor((target - today) / 86400000) + 1) : 0;
      availableCapacity = capacity * daysRemaining;
    }
    var backlog = hasDeadline ? Math.max(0, weakCount - availableCapacity) : 0;
    return {
      schema_version: SCHEMA_VERSION,
      generated_at: current,
      settings: normalized,
      items: selected,
      total_candidates: records.length,
      overload: {
        is_overloaded: hasDeadline && backlog > 0,
        backlog: backlog,
        required: weakCount,
        available_capacity: availableCapacity,
        days_remaining: daysRemaining,
      },
    };
  }

  function exportData(storage, datasetVersion) {
    var ledger = getLedger(storage);
    if (ledger.write_blocked) throw new Error(ledger.storage_error);
    return JSON.stringify({
      schema_version: SCHEMA_VERSION,
      dataset_version: datasetVersion || null,
      ledger: ledger,
      settings: getSettings(storage),
    }, null, 2);
  }

  function importData(value, storage) {
    var payload = typeof value === 'string' ? JSON.parse(value) : value;
    if (!payload || payload.schema_version !== SCHEMA_VERSION || !payload.ledger || !Array.isArray(payload.ledger.attempts)
        || (payload.ledger.schema_version != null && payload.ledger.schema_version !== SCHEMA_VERSION)) {
      throw new Error('無法匯入：複習資料格式不相容');
    }
    var attempts = payload.ledger.attempts.map(function (item, index) {
      if (!validAttempt(item)) throw new Error('無法匯入：第 ' + (index + 1) + ' 筆作答紀錄格式錯誤，原資料未變更');
      // Canonicalize timestamps: lexicographic ordering only works on ISO text.
      return Object.assign({}, item, { attempted_at: parseDate(item.attempted_at).toISOString() });
    });
    // Validate the whole backup before replacing any existing data. Never
    // silently trim imported history to the normal recording retention limit.
    if (compactAttempts(attempts).length !== attempts.length) {
      throw new Error('無法匯入：單題作答紀錄超過 ' + MAX_ATTEMPTS_PER_QUESTION + ' 筆上限，原資料未變更');
    }
    if (payload.settings != null && (typeof payload.settings !== 'object' || Array.isArray(payload.settings))) {
      throw new Error('無法匯入：複習設定格式錯誤，原資料未變更');
    }
    var ledger = { schema_version: SCHEMA_VERSION, attempts: attempts };
    var settings = normalizeSettings(payload.settings || DEFAULT_SETTINGS);
    var ledgerJson = JSON.stringify(ledger);
    var settingsJson = JSON.stringify(settings);
    var target = storageOrDefault(storage);
    if (!target) throw new Error('匯入失敗：本機儲存空間無法使用');
    var existingLedger = getLedger(storage);
    if (existingLedger.write_blocked) throw new Error(existingLedger.storage_error);
    var previousLedger = target.getItem(LEDGER_KEY);
    var ledgerWritten = false;
    try {
      target.setItem(LEDGER_KEY, ledgerJson);
      ledgerWritten = true;
      target.setItem(SETTINGS_KEY, settingsJson);
    } catch (e) {
      // localStorage.setItem is individually atomic. If the second key fails,
      // restore the first. This is error recovery, not a cross-tab/crash lock.
      if (ledgerWritten) {
        try {
          if (previousLedger == null) target.removeItem(LEDGER_KEY);
          else target.setItem(LEDGER_KEY, previousLedger);
        } catch (rollbackError) {
          throw new Error('匯入失敗且無法還原原資料；請保留備份並檢查本機儲存空間');
        }
      }
      throw new Error('匯入失敗：本機儲存空間不足或無法寫入，原資料已保留');
    }
    return { ledger: ledger, settings: settings };
  }

  function clearLearnerData(storage) {
    var target = storageOrDefault(storage);
    if (!target) return;
    try {
      target.removeItem(LEDGER_KEY);
      target.removeItem(LEDGER_KEY + '.corrupt');
      target.removeItem(SETTINGS_KEY);
      target.removeItem(HISTORY_KEY);
    } catch (e) {}
  }

  window.ReviewQueue = {
    schemaVersion: SCHEMA_VERSION,
    reasonLabels: REASON_LABELS,
    getLedger: getLedger,
    saveLedger: saveLedger,
    getSettings: getSettings,
    saveSettings: saveSettings,
    normalizeSettings: normalizeSettings,
    questionIdentity: questionIdentity,
    contentHash: contentHash,
    recordQuizAttempt: recordQuizAttempt,
    saveQuizSummary: saveQuizSummary,
    deriveReviewState: deriveReviewState,
    buildReviewQueue: buildReviewQueue,
    exportData: exportData,
    importData: importData,
    clearLearnerData: clearLearnerData,
  };
})(window);
