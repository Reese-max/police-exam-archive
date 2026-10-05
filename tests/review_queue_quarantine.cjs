const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const key = 'exam-attempt-ledger-v1';
const backupKey = key + '.corrupt';
const raw = '{' + 'x'.repeat(6000);
const question = { cat: 'fixture', yr: 115, sub: 'synthetic', no: '1', idx: 0,
  type: 'choice', stem: 'fixture only', optA: 'A', optB: 'B', optC: 'C', optD: 'D', ans: 'A' };
const window = {};
vm.runInNewContext(fs.readFileSync(path.join(__dirname, '..', '考古題網站/js/review-queue.js'), 'utf8'), { window });
const rq = window.ReviewQueue;
const empty = { schema_version: 1, attempts: [] };
const payload = { schema_version: 1, ledger: empty, settings: { daily_question_limit: 5 } };
const options = { attemptedAt: '2026-10-05T12:00:00.000Z', datasetVersion: 'synthetic-v1' };

function storage(mode = 'quota') {
  const values = new Map([[key, raw], ['unrelated', 'sentinel']]);
  const writes = [];
  return {
    values, writes, capacity: mode === 'quota' ? 8000 : 20000,
    getItem(k) {
      if (mode === 'unreadable' && k === key) throw Error('read denied');
      if (mode === 'readback' && k === backupKey && writes.includes(backupKey)) throw Error('readback denied');
      return values.has(k) ? values.get(k) : null;
    },
    setItem(k, v) {
      writes.push(k);
      if (mode === 'throw' && k === backupKey) throw Error('quarantine denied');
      if (mode === 'noop' && k === backupKey) return;
      const candidate = new Map(values); candidate.set(k, String(v));
      const bytes = [...candidate.values()].reduce((n, value) => n + Buffer.byteLength(value), 0);
      if (bytes > this.capacity) throw Error('QuotaExceededError');
      values.set(k, String(v));
    },
    removeItem(k) { values.delete(k); },
  };
}
function preserved(s) {
  assert.equal(s.values.get(key), raw, 'original malformed bytes must remain');
  assert.equal(s.values.get('unrelated'), 'sentinel');
  assert.ok(!s.writes.includes(key), 'blocked operation must not attempt a replacement');
}
const record = s => rq.recordQuizAttempt([question], ['B'], [false], options, s);
const cases = {
  quota_record() {
    const s = storage();
    // The dangerous replacement genuinely fits; the duplicate quarantine does not.
    const control = storage('success'); control.values.delete(key); record(control);
    assert.ok(Buffer.byteLength(control.values.get(key)) + Buffer.byteLength('sentinel') < s.capacity);
    assert.ok(2 * Buffer.byteLength(raw) + Buffer.byteLength('sentinel') > s.capacity);
    assert.equal(record(s).persisted, false);
    preserved(s); assert.equal(s.values.get(backupKey), undefined);
  },
  quota_direct_save() {
    const s = storage(); assert.equal(rq.saveLedger(empty, s), false); preserved(s);
  },
  quota_import() {
    const s = storage(); assert.throws(() => rq.importData(payload, s), /隔離|原資料/); preserved(s);
    assert.equal(s.values.get('exam-review-settings-v1'), undefined);
  },
  quota_export() {
    const s = storage(); assert.throws(() => rq.exportData(s, 'fixture'), /隔離|原資料/); preserved(s);
  },
  quarantine_throw() {
    const s = storage('throw'); assert.equal(record(s).persisted, false); preserved(s);
  },
  quarantine_noop() {
    const s = storage('noop'); assert.equal(record(s).persisted, false); preserved(s);
  },
  quarantine_readback() {
    const s = storage('readback'); assert.equal(record(s).persisted, false); preserved(s);
  },
  unreadable_source() {
    const s = storage('unreadable'); assert.equal(record(s).persisted, false); preserved(s);
  },
  blocked_read_is_usable() {
    const s = storage(); const ledger = rq.getLedger(s);
    assert.equal(ledger.write_blocked, true); assert.match(ledger.storage_error, /原資料|隔離/);
    assert.equal(ledger.attempts.length, 0);
    assert.doesNotThrow(() => rq.buildReviewQueue([question], ledger, {}, options.attemptedAt, 'fixture'));
    preserved(s);
  },
  quota_recovery_once() {
    const s = storage(); assert.equal(record(s).persisted, false); preserved(s);
    s.capacity = 20000;
    assert.equal(record(s).persisted, true);
    assert.equal(s.values.get(backupKey), raw);
    assert.equal(rq.getLedger(s).attempts.length, 1, 'retry records exactly one event');
    assert.equal(JSON.parse(rq.exportData(s)).ledger.attempts.length, 1);
  },
  already_quarantined() {
    const s = storage(); s.values.set(backupKey, raw);
    assert.equal(record(s).persisted, true);
    assert.equal(s.values.get(backupKey), raw);
    assert.ok(!s.writes.includes(backupKey), 'an exact existing quarantine needs no rewrite');
  },
  successful_quarantine_import() {
    const s = storage('success'); rq.importData(payload, s);
    assert.equal(s.values.get(backupKey), raw);
    assert.equal(rq.getLedger(s).attempts.length, 0);
    assert.equal(rq.getSettings(s).daily_question_limit, 5);
    assert.equal(s.values.get('unrelated'), 'sentinel');
  },
  invalid_backup_has_no_side_effects() {
    const s = storage();
    assert.throws(() => rq.importData({ ...payload, settings: 'invalid' }, s), /格式/);
    preserved(s); assert.equal(s.writes.length, 0, 'validate the complete backup before quarantine or replacement');
  },
};
const name = process.argv[2]; assert.ok(Object.hasOwn(cases, name), 'known fixture case');
cases[name](); console.log(JSON.stringify({ case: name, passed: true, synthetic_storage_only: true }));
