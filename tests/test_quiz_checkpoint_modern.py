"""Current answer, passage and image contracts must survive #69 recovery."""
import json

import pytest

from test_quiz_checkpoint import NODE_PRELUDE, assert_node_ok, run_node
from test_quiz_session_flow import run_flow


MODERN = """
function modernState() {
  const state = inProgressState();
  state.questions = state.questions.map(q => ({
    subj: q.subj, stem: q.stem, opts: q.opts,
    passage: '閱讀 [[1]] &lt;文章&gt;',
    accepted: [0, 2], bonus: false, answerLabel: 'A或C',
    imageOpts: [
      {src:'水上警察學系/images/q2-option-A.png', alt:'甲 &quot;圖&quot;', sourcePage:'2'},
      {src:'', alt:'', sourcePage:''}, {src:'', alt:'', sourcePage:''}, {src:'', alt:'', sourcePage:''}
    ]
  }));
  return state;
}
"""


def test_current_answer_passage_image_contract_roundtrip():
    assert_node_ok(run_node(NODE_PRELUDE + MODERN + """
        const store = memStore(); const state = modernState();
        assert.strictEqual(QC.save(state, store, NOW), true, 'current questions must checkpoint');
        const recovered = QC.load(store, NOW + 17000);
        assert.deepStrictEqual(recovered.questions, state.questions);
        assert.deepStrictEqual(recovered.answers, state.answers);
        assert.strictEqual(recovered.remain, state.remain - 17);
        state.questions[0].bonus = true;
        state.questions[0].accepted = [0,1,2,3];
        state.questions[0].answerLabel = '送分';
        assert.strictEqual(QC.save(state, store, NOW), true, 'bonus contract must checkpoint');
        console.log('modern-ok');
    """), 'modern-ok')


@pytest.mark.parametrize('mutation', [
    'q.accepted=[]', 'q.accepted=[0,4]', 'q.accepted=[0,0]',
    'q.bonus="true"', 'q.bonus=true', 'q.answerLabel="B"',
    'q.passage="<img src=x onerror=alert(1)>"',
    'q.imageOpts[0].alt=\'<img src=x>\'',
    'q.imageOpts[0].alt=\'" onerror="alert(1)\'',
    'q.imageOpts[0].sourcePage=\'2" onerror="alert(1)\'',
    'q.imageOpts[0].src="javascript:alert(1)"',
    'q.imageOpts[0].src="data:image/svg+xml,<svg onload=alert(1)>"',
    'q.imageOpts[0].src="//evil.example/image.png"',
    'q.imageOpts[0].src="https://evil.example/image.png"',
    'q.imageOpts[0].src="../outside.png"',
    'q.imageOpts[0].src="cat/images/%2e%2e/evil.png"',
    'q.imageOpts[0].src=\'cat/images/x.png" onerror="alert(1)\'',
])
def test_corrupt_current_metadata_is_rejected_and_cleared(mutation):
    assert_node_ok(run_node(NODE_PRELUDE + MODERN + """
        const store=memStore(); const state=modernState();
        assert.ok(QC.save(state, store, NOW), 'valid modern baseline');
        const snap=JSON.parse(store.getItem(QC.KEY)); const q=snap.questions[0];
    """ + mutation + ";" + """
        store.setItem(QC.KEY, JSON.stringify(snap));
        assert.strictEqual(QC.load(store, NOW), null, 'tampered metadata must fail closed');
        assert.strictEqual(store.getItem(QC.KEY), null);
        console.log('reject-ok');
    """), 'reject-ok')


def current_pool(answer='A或C', image='水上警察學系/images/q2-option-A.png'):
    return [dict(yr=115, sub='現代答案', stem='題幹', passage='閱讀 [[1]] <段落>',
                 optA='甲', optB='乙', optC='丙', optD='丁', ans=answer,
                 optImageA=image, optAltA='選項 "圖片"', sourcePage='2')] * 12


@pytest.mark.parametrize('pool_size,preset', [(1, 10), (9, 10), (12, 20), (25, 30), (40, 50), (49, 50), (50, 50)])
def test_nonpreset_restored_exam_keeps_a_valid_count_for_finish_retry(pool_size, preset):
    run_flow("""
        const store=readStore(); const clock={value:T0};
        const pool=%s;
        const page=createQuizPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:store,clock,pool});
        page.selectSeg('segCount',50); page.selectSeg('segTime',60); page.click('startBtn');
        assert.strictEqual(page.state().total,%s,'confirmed short pool starts with available questions');
        page.choose(2); page.pagehide(); const expected=page.checkpoint();
        const recovered=createQuizPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:store,clock,pool});
        recovered.click('resumeBtn');
        assert.deepStrictEqual(JSON.parse(JSON.stringify(recovered.checkpoint().questions)),expected.questions);
        assert.strictEqual(recovered.state().total,%s,'recovery cannot change the active exam size');
        assert.strictEqual(recovered.read("document.querySelector('#segCount .on').dataset.v"),'%s');
        assert.strictEqual(recovered.get('segCount').children.length,4,'do not inject a raw checkpoint count button');
        recovered.click('submitBtn'); recovered.click('retryBtn'); recovered.click('startBtn');
        assert.strictEqual(recovered.state().view,'exam','retry starts without a null count selection');
        assert.strictEqual(recovered.state().total,Math.min(%s,%s));
        assert.ok(recovered.checkpoint(),'new retry is checkpointable');
        console.log('flow-ok');
    """ % (json.dumps((current_pool() * 5)[:pool_size], ensure_ascii=False),
           pool_size, pool_size, preset, pool_size, preset))


def test_real_page_recovers_alternative_answers_passage_and_image_without_downgrade():
    run_flow("""
        const store=readStore(); const clock={value:T0};
        const page=createQuizPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:store,clock,pool:%s});
        page.selectSeg('segCount',10); page.selectSeg('segTime',60); page.click('startBtn');
        assert.ok(page.checkpoint(), 'current mode is saved');
        assert.ok(page.get('qPassage').innerHTML.includes('<mark>[1]</mark>'));
        assert.ok(page.get('qPassage').innerHTML.includes('&lt;段落&gt;'));
        assert.ok(page.get('choices').innerHTML.includes('q2-option-A.png'));
        const link=page.get('choices').children.find(el=>el.tagName==='A');
        const radio=page.get('choices').children.find(el=>el.classes.has('choice'));
        radio.dispatch('click',{target:link,preventDefault(){}});
        assert.strictEqual(page.state().answers[0],null,'image link does not pick a choice');
        for(let i=0;i<10;i++){page.goto(i);page.choose(2);}
        page.goto(4); page.click('flagBtn'); page.tick(17); page.pagehide();
        const expected=page.checkpoint(); clock.value+=11000;
        const recovered=open(store,clock); recovered.click('resumeBtn');
        assert.strictEqual(recovered.state().view,'exam');
        assert.strictEqual(recovered.state().remain,3600-28);
        assert.deepStrictEqual(JSON.parse(JSON.stringify(recovered.checkpoint().questions)),expected.questions);
        assert.ok(recovered.get('qPassage').innerHTML.includes('<mark>[1]</mark>'));
        assert.ok(recovered.get('choices').innerHTML.includes('q2-option-A.png'));
        assert.strictEqual(recovered.state().flags[4],true);
        recovered.click('submitBtn'); assert.strictEqual(recovered.state().scorePct,'100%%');
        assert.strictEqual(store.getItem(KEY),null); page.pagehide();
        assert.strictEqual(store.getItem(KEY),null,'old owner cannot resurrect completed current exam');
        console.log('flow-ok');
    """ % json.dumps(current_pool(), ensure_ascii=False))


def test_real_page_bonus_unanswered_questions_still_score_after_recovery():
    run_flow("""
        const store=readStore(); const clock={value:T0};
        const page=createQuizPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:store,clock,pool:%s});
        page.selectSeg('segCount',10); page.click('startBtn'); page.pagehide();
        const recovered=open(store,clock); recovered.click('resumeBtn');
        assert.strictEqual(recovered.state().view,'exam');
        assert.ok(recovered.checkpoint().questions.every(q=>q.bonus && q.accepted.length===4));
        recovered.click('submitBtn'); assert.strictEqual(recovered.state().scorePct,'100%%');
        assert.strictEqual(recovered.get('sSkip').textContent,'0');
        console.log('flow-ok');
    """ % json.dumps(current_pool('送分'), ensure_ascii=False))


def test_current_recovery_changes_owner_even_at_the_same_wall_clock_instant():
    run_flow("""
        const store=readStore(); const clock={value:T0};
        const original=createQuizPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:store,clock,pool:%s});
        original.selectSeg('segCount',10); original.click('startBtn'); original.choose(0);
        const previousOwner=original.checkpoint().sessionId;
        const recovered=open(store,clock); recovered.click('resumeBtn'); recovered.choose(2);
        assert.notStrictEqual(recovered.checkpoint().sessionId,previousOwner);
        const current=store.getItem(KEY); original.pagehide();
        assert.strictEqual(store.getItem(KEY),current,'old page cannot replace the new owner answer');
        recovered.click('submitBtn'); original.pagehide();
        assert.strictEqual(store.getItem(KEY),null,'old page cannot resurrect a completed current exam');
        console.log('flow-ok');
    """ % json.dumps(current_pool(), ensure_ascii=False))


def test_real_pool_excludes_missing_invalid_answers_and_canonicalizes_valid_label():
    pool = current_pool(' A或C ')
    for invalid in ['', '或', 'A或', 'A或Z', 'AB']:
        pool.append({**pool[0], 'ans': invalid})
    run_flow("""
        const page=createQuizPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:readStore(),clock:{value:T0},pool:%s});
        assert.strictEqual(page.get('matchCount').textContent,'12 題','unscorable source answers must stay out of pool');
        page.selectSeg('segCount',10); page.click('startBtn');
        assert.ok(page.checkpoint(), 'normalized valid source labels remain checkpointable');
        assert.ok(page.checkpoint().questions.every(q=>q.answerLabel==='A或C' && q.accepted.join(',')==='0,2'));
        console.log('flow-ok');
    """ % json.dumps(pool, ensure_ascii=False))


def test_real_page_legacy_v1_integer_answer_restores_and_upgrades():
    run_flow("""
        const {store,clock,page}=context(); startWorkedExam(page);
        const snap=page.checkpoint(); snap.v=1; delete snap.sessionId;
        snap.questions=snap.questions.map(q=>({subj:q.subj,stem:q.stem,opts:q.opts,ans:q.accepted[0]}));
        store.setItem(KEY,JSON.stringify(snap));
        const recovered=open(store,clock); recovered.click('resumeBtn');
        assert.strictEqual(recovered.state().view,'exam');
        assert.deepStrictEqual(recovered.state().answers,page.state().answers);
        assert.deepStrictEqual(recovered.state().flags,page.state().flags);
        assert.strictEqual(recovered.state().cur,4);
        assert.ok(recovered.checkpoint().questions.every(q=>q.accepted.length===1 && q.bonus===false));
        recovered.click('submitBtn'); assert.strictEqual(recovered.state().view,'result');
        assert.strictEqual(store.getItem(KEY),null);
        console.log('flow-ok');
    """)


@pytest.mark.parametrize('image', ['javascript:alert(1)', '//evil.example/x.png', '../x.png',
                                  'cat/images/x.png" onerror="alert(1)', 'cat/images/%2e%2e/x.png'])
def test_raw_source_image_path_cannot_inject_active_or_external_markup(image):
    run_flow("""
        const page=createQuizPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:readStore(),clock:{value:T0},pool:%s});
        page.selectSeg('segCount',10); page.click('startBtn');
        assert.ok(page.checkpoint(), 'invalid optional image does not break a valid question');
        assert.ok(page.checkpoint().questions.every(q=>q.imageOpts[0].src===''));
        assert.ok(!page.get('choices').innerHTML.includes('<img'), 'unsafe source produces no image markup');
        console.log('flow-ok');
    """ % json.dumps(current_pool(image=image), ensure_ascii=False))
