/* Minimal DOM harness for driving 考古題網站/quiz.html under Node.
 *
 * The repository's enforced gate is `python3 -m pytest -q`; the nested
 * Playwright suite is not part of it.  This harness extracts the real inline
 * exam script out of quiz.html and runs it in a `vm` context backed by a small
 * DOM stub, so the checkpoint lifecycle (start → answer/flag → checkpoint →
 * reload → resume → finish) is executed rather than pattern-matched.
 *
 * createQuizPage({ html, checkpointJs, storage, now }) → driver
 */
'use strict';

const fs = require('fs');
const vm = require('vm');
const { IDBFactory } = require('./node_modules/fake-indexeddb');
const databases = new WeakMap();

function databaseFor(storage) {
  if (!databases.has(storage)) databases.set(storage, new IDBFactory());
  return databases.get(storage);
}

const CLOCK = { value: 1760000000000 };
let sessionSequence = 0;

function readStore(storage) {
  const store = new Map();
  return {
    getItem: (k) => (store.has(k) ? store.get(k) : null),
    setItem: (k, v) => { store.set(k, String(v)); },
    removeItem: (k) => { store.delete(k); },
    _dump: () => Object.fromEntries(store),
  };
}

/* Create a fake element.  innerHTML assignments are scanned for
 * `data-i="N"` so the listeners quiz.html attaches to rendered choices and
 * mini-nav buttons are reachable. */
function makeElement(doc, id) {
  let text = '';
  const el = {
    id: id,
    tagName: 'DIV',
    get textContent() { return text; },
    set textContent(value) { text = value === null || value === undefined ? '' : String(value); },
    _innerHTML: '',
    value: '',
    disabled: false,
    dataset: {},
    style: {},
    children: [],
    classes: new Set(),
    listeners: {},
    classList: {
      add(...names) { names.forEach((n) => el.classes.add(n)); },
      remove(...names) { names.forEach((n) => el.classes.delete(n)); },
      contains(name) { return el.classes.has(name); },
      toggle(name, force) {
        const on = force === undefined ? !el.classes.has(name) : !!force;
        if (on) el.classes.add(name); else el.classes.delete(name);
        return on;
      },
    },
    appendChild(child) { el.children.push(child); child.parent = el; return child; },
    addEventListener(name, fn) {
      (el.listeners[name] = el.listeners[name] || []).push(fn);
    },
    dispatch(name, event) {
      // Events bubble: quiz.html binds delegated handlers on containers
      // (segmented controls) while the event target is the inner <button>.
      const target = (event && event.target) || el;
      const ev = event || { target: target, preventDefault() {} };
      let node = el;
      const pending = [];
      while (node) {
        (node.listeners[name] || []).forEach((fn) => pending.push(fn.call(node, ev)));
        node = node.parent || null;
      }
      return Promise.all(pending);
    },
    set innerHTML(html) {
      el._innerHTML = html;
      el.children = [];
      const re = /<(\w+)([^>]*?)>/g;
      let m;
      while ((m = re.exec(html)) !== null) {
        const attrs = m[2];
        const dataI = /data-i="(\d+)"/.exec(attrs);
        const classAttr = /class="([^"]*)"/.exec(attrs);
        const child = makeElement(doc, '');
        child.tagName = m[1].toUpperCase();
        if (dataI) child.dataset.i = dataI[1];
        if (classAttr) classAttr[1].split(/\s+/).filter(Boolean).forEach((c) => child.classes.add(c));
        el.children.push(child);
        child.parent = el;
      }
    },
    get innerHTML() { return el._innerHTML; },
    querySelectorAll(sel) {
      const want = sel.replace(/^[.#]/, '');
      return el.children.filter((c) => c.classes.has(want) || c.tagName === want.toUpperCase());
    },
    querySelector(sel) {
      const want = sel.replace(/^[.#]/, '');
      return el.children.find((c) => c.classes.has(want)) || null;
    },
    closest(selector) {
      let node = el;
      while (node) {
        if (selector.startsWith('.') ? node.classes.has(selector.slice(1)) : node.tagName === selector.toUpperCase()) return node;
        node = node.parent || null;
      }
      return null;
    },
  };
  (el.classes).add;
  return el;
}

function createQuizPage(options) {
  const html = options.html;
  const storage = options.storage || readStore(null);
  const clock = options.clock || CLOCK;
  const doc = {};
  const elements = Object.create(null);

  const get = (id) => {
    if (!(id in elements)) elements[id] = makeElement(doc, id);
    return elements[id];
  };

  // Seed the elements quiz.html declares, including the segmented controls,
  // so `document.querySelector('#segTime .on')` resolves from real markup.
  const idRe = /<([a-zA-Z][\w-]*)([^>]*\sid="([A-Za-z0-9_]+)"[^>]*)>/g;
  let idMatch;
  while ((idMatch = idRe.exec(html)) !== null) {
    const el = get(idMatch[3]);
    el.tagName = idMatch[1].toUpperCase();
    const classAttr = /class="([^"]*)"/.exec(idMatch[2]);
    if (classAttr) classAttr[1].split(/\s+/).filter(Boolean).forEach((c) => el.classes.add(c));
  }
  const segRe = /<div class="seg" id="([A-Za-z0-9_]+)">([\s\S]*?)<\/div>/g;
  let segMatch;
  while ((segMatch = segRe.exec(html)) !== null) {
    const seg = get(segMatch[1]);
    const buttonRe = /<button([^>]*)>/g;
    let buttonMatch;
    while ((buttonMatch = buttonRe.exec(segMatch[2])) !== null) {
      const attrs = buttonMatch[1];
      const value = /data-v="([^"]+)"/.exec(attrs);
      const classAttr = /class="([^"]*)"/.exec(attrs);
      const button = makeElement(doc, '');
      button.tagName = 'BUTTON';
      if (value) button.dataset.v = value[1];
      if (classAttr) classAttr[1].split(/\s+/).filter(Boolean).forEach((c) => button.classes.add(c));
      button.parent = seg;
      seg.children.push(button);
    }
  }

  doc._listeners = {};
  const attrs = Object.create(null);
  doc.documentElement = {
    setAttribute: (name, value) => { attrs[name] = value; },
    getAttribute: (name) => (name in attrs ? attrs[name] : null),
  };
  doc.getElementById = get;
  doc.createElement = (tag) => makeElement(doc, '');
  doc.querySelector = (sel) => {
    const m = /^#([A-Za-z0-9_]+)\s+\.([A-Za-z0-9_-]+)$/.exec(sel);
    if (!m) return null;
    const parent = get(m[1]);
    return parent.children.find((c) => c.classes.has(m[2])) || null;
  };
  doc.querySelectorAll = () => [];
  doc.addEventListener = (name, fn) => { (doc._listeners[name] = doc._listeners[name] || []).push(fn); };
  doc.dispatch = (name, event) => Promise.all((doc._listeners[name] || []).map((fn) => fn(event)));
  doc.visibilityState = 'visible';

  const timers = [];
  const sandbox = {
    document: doc,
    navigator: {},
    localStorage: storage,
    indexedDB: options.indexedDB === undefined ? databaseFor(storage) : options.indexedDB,
    console: console,
    JSON: JSON,
    Math: Math,
    isFinite: isFinite,
    parseInt: parseInt,
    parseFloat: parseFloat,
    Number: Number,
    String: String,
    Array: Array,
    Object: Object,
    Boolean: Boolean,
    Error: Error,
    setTimeout: () => 0,
    clearTimeout: () => {},
    setInterval: (fn) => { timers.push(fn); return timers.length; },
    clearInterval: (handle) => { timers[handle - 1] = null; },
    alert: () => {},
    confirm: () => true,
  };
  sandbox._listeners = {};
  sandbox.window = sandbox;
  sandbox.self = sandbox;
  sandbox.scrollTo = () => {};
  sandbox.matchMedia = () => ({ matches: false });
  sandbox.addEventListener = (name, fn) => { (sandbox._listeners[name] = sandbox._listeners[name] || []).push(fn); };
  sandbox.dispatch = (name, event) => Promise.all((sandbox._listeners[name] || []).map((fn) => fn(event)));
  sandbox.crypto = { randomUUID: () => 'session-' + clock.value + '-' + (++sessionSequence) };

  vm.createContext(sandbox);
  // Date.now() reads the shared clock, so advancing it affects every open page
  // the way a real wall clock would. The host Date is deliberately NOT injected
  // into the sandbox: each vm context owns its own Date intrinsic, so patching
  // it here cannot leak into another page (or into the host realm).
  sandbox.__clockRef = clock;
  vm.runInContext('Date.now = function () { return globalThis.__clockRef.value; };', sandbox);

  // Question bank stub: SearchEngine is served from a separate file that the
  // harness does not need; the pool shape is what buildQuestions consumes.
  const POOL_SIZE = 60;
  const pool = options.pool || Array.from({ length: POOL_SIZE }, (_, i) => ({
    yr: 110 + (i % 5),
    sub: '測試科目' + (i % 3),
    stem: '第' + (i + 1) +'題題幹',
    optA: '選項甲' + i, optB: '選項乙' + i, optC: '選項丙' + i, optD: '選項丁' + i,
    ans: 'ABCD'[i % 4],
  }));
  sandbox.SearchEngine = {
    // Synchronous thenable: quiz.html only chains .then().catch() on this,
    // and a real Promise would resolve after the harness has finished driving.
    loadIndex: () => ({ then(fn) { fn({}); return this; }, catch() { return this; } }),
    getFacets: () => ({ categories: ['行政警察'], years: [110, 111, 112, 113, 114], subjects: ['測試科目1'] }),
    search: () => pool.map((q) => Object.assign({}, q)),
  };

  // Load the real source contract, just as quiz.html does before its inline script.
  const answerUtilsJs = require('path').join(require('path').dirname(options.checkpointJs), 'answer-utils.js');
  vm.runInContext(fs.readFileSync(answerUtilsJs, 'utf8'), sandbox, { filename: 'answer-utils.js' });
  vm.runInContext(fs.readFileSync(options.checkpointJs, 'utf8'), sandbox, { filename: 'quiz-checkpoint.js' });

  const inlineRe = /<script(?![^>]*\ssrc=)[^>]*>([\s\S]*?)<\/script>/g;
  const inline = [];
  let inlineMatch;
  while ((inlineMatch = inlineRe.exec(html)) !== null) {
    if (inlineMatch[1].trim()) inline.push(inlineMatch[1]);
  }
  inline.forEach((code, index) => vm.runInContext(code, sandbox, { filename: 'quiz-inline-' + index + '.js' }));

  const page = {
    context: sandbox,
    storage: storage,
    doc: doc,
    get: get,
    setNow(ms) { clock.value = ms; },
    now() { return clock.value; },
    ready() { return vm.runInContext('checkpointReady', sandbox); },
    click(id) { return get(id).dispatch('click', { target: get(id), preventDefault() {} }); },
    choose(index) { return get('choices').children.find((c) => c.dataset.i === String(index)).dispatch('click'); },
    goto(index) { return get('miniGrid').children.find((c) => c.dataset.i === String(index)).dispatch('click'); },
    selectSeg(segId, value) {
      return get(segId).children.find((c) => c.dataset.v === String(value)).dispatch('click');
    },
    // One tick == one second of wall clock, so timed writes and the wall-clock
    // deduction behave the way they do in the browser.
    async tick(times) {
      for (let i = 0; i < (times || 1); i++) {
        clock.value += 1000;
        await Promise.all(timers.slice().map((fn) => fn && fn()));
      }
    },
    running() { return timers.some((fn) => fn !== null); },
    timers: timers,
    read(expression) { return vm.runInContext(expression, sandbox); },
    hide() { doc.visibilityState = 'hidden'; return doc.dispatch('visibilitychange', { type: 'visibilitychange' }); },
    pagehide() { return sandbox.dispatch('pagehide', { type: 'pagehide' }); },
    async authoritative() { return sandbox.QuizCheckpoint.persistence.read(); },
    checkpoint() {
      const raw = storage.getItem(sandbox.QuizCheckpoint ? sandbox.QuizCheckpoint.KEY : 'exam-quiz-active');
      return raw === null ? null : JSON.parse(raw);
    },
    state() {
      const s = sandbox;
      const view = ['setup', 'exam', 'result'].find((name) => !get(name + 'View').classes.has('hidden'));
      return {
        view: view,
        cur: page.read('cur'),
        total: page.read('total'),
        remain: page.read('remain'),
        elapsed: page.read('elapsed'),
        durSec: page.read('durSec'),
        examDone: page.read('examDone'),
        answers: Array.from(page.read('answers') || []),
        flags: Array.from(page.read('flags') || []),
        stems: Array.from(page.read('questions') || []).map((q) => q.stem),
        timerText: get('timerText').textContent,
        timerWarn: get('timer').classes.has('warn'),
        bannerHidden: get('resumeBanner').classes.has('hidden'),
        resumeInfo: get('resumeInfo').textContent,
        stem: get('qStem').innerHTML,
        curNum: get('curNum').textContent,
        totalNum: get('totalNum').textContent,
        matchCount: get('matchCount').textContent,
        scorePct: get('scorePct').textContent,
        resultTitle: get('resultTitle').textContent,
        choiceCount: get('choices').querySelectorAll('.choice').length,
        selectedChoice: (get('choices').children.find((c) => c.classes.has('sel')) || { dataset: {} }).dataset.i,
      };
    },
  };
  return page;
}

module.exports = { createQuizPage, readStore, databaseFor, CLOCK };
