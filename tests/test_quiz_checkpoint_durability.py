"""Cross-renderer stale caches and transaction completion are different contracts.

The page runs its original handlers. IndexedDB is the independent, pinned
fake-indexeddb implementation; real Edge durability is verified separately.
"""
from test_quiz_session_flow import run_flow


def test_accepted_answer_survives_immediate_reopen_and_a_legacy_renderer_write():
    run_flow("""
        const {store,clock,page}=await context();
        await startWorkedExam(page);
        const oldRaw=store.getItem(KEY);
        const staleCache=readStore(); staleCache.setItem(KEY,oldRaw);
        const oldState=JSON.parse(oldRaw);
        const recovered=await open(store,clock);
        await recovered.click('resumeBtn'); await recovered.goto(2);
        const acceptance=recovered.choose(3);
        assert.notStrictEqual(recovered.state().selectedChoice,'3','not accepted before transaction completion');
        await acceptance;
        assert.strictEqual(recovered.state().selectedChoice,'3','original selected radio acknowledges the completed write');
        assert.strictEqual(recovered.get('checkpointStatus').dataset.state,'saved');
        const committed=await recovered.authoritative();
        assert.strictEqual(committed.answers[2],3);
        assert.notStrictEqual(committed.sessionId,oldState.sessionId);
        // A pre-upgrade renderer still sees its cached owner and its old
        // synchronous CAS succeeds. Persist that actual legacy write after
        // the resumed page has accepted the answer; the DB must ignore it.
        const QC=page.context.QuizCheckpoint;
        assert.strictEqual(QC.save(oldState,staleCache,clock.value,oldState.sessionId),true);
        store.setItem(KEY,staleCache.getItem(KEY));
        assert.strictEqual(JSON.parse(store.getItem(KEY)).answers[2],2,'old mirror really overwrote its LS slot');
        const reopened=await open(store,clock);
        const durable=await reopened.authoritative();
        assert.strictEqual(durable.sessionId,committed.sessionId,'stale LS cannot retake the owner');
        assert.strictEqual(durable.answers[2],3,'immediate reopen retains the already accepted answer');
        await reopened.click('resumeBtn');
        assert.strictEqual(reopened.state().answers[2],3);
        console.log('flow-ok');
    """)


def test_claim_reads_the_latest_answer_in_its_transaction():
    run_flow("""
        const {store,clock,page}=await context(); await startWorkedExam(page);
        const recovery=await open(store,clock);
        await page.goto(2); await page.choose(3); // after recovery's banner
        await recovery.click('resumeBtn');
        assert.strictEqual(recovery.state().answers[2],3,'claim must not copy the stale banner snapshot');
        assert.strictEqual((await recovery.authoritative()).answers[2],3);
        console.log('flow-ok');
    """)


def test_two_simultaneous_recovery_clicks_only_grant_one_owner():
    run_flow("""
        const {store,clock,page}=await context(); await startWorkedExam(page);
        const a=await open(store,clock), b=await open(store,clock);
        await Promise.all([a.click('resumeBtn'),b.click('resumeBtn')]);
        const winners=[a,b].filter(p=>p.state().view==='exam');
        assert.strictEqual(winners.length,1,'two DB connections cannot both claim the offered owner');
        const loser=[a,b].find(p=>p!==winners[0]);
        assert.strictEqual(loser.state().view,'setup');
        assert.ok(loser.get('resumeNote').textContent.includes('另一個分頁'));
        await winners[0].goto(2); await winners[0].choose(3);
        await page.goto(6); await page.tick(6); await page.pagehide();
        assert.strictEqual((await winners[0].authoritative()).answers[2],3);
        assert.strictEqual(page.get('checkpointStatus').dataset.state,'conflict');
        console.log('flow-ok');
    """)


def test_completed_tombstone_ignores_a_later_legacy_snapshot():
    run_flow("""
        const {store,clock,page}=await context(); await startWorkedExam(page);
        const legacy=store.getItem(KEY);
        const recovery=await open(store,clock); await recovery.click('resumeBtn');
        await recovery.click('submitBtn');
        store.setItem(KEY,legacy); // historical pagehide writes after completion
        const reopened=await open(store,clock);
        assert.strictEqual(await reopened.authoritative(),null,'closed record blocks re-import');
        assert.strictEqual(reopened.state().bannerHidden,true);
        await reopened.click('startBtn');
        assert.ok(await reopened.authoritative(),'an explicit new exam can replace a tombstone');
        console.log('flow-ok');
    """)


def test_legacy_import_occurs_once_and_later_mirror_deletion_cannot_erase_it():
    run_flow("""
        const {store,clock,page}=await context(); await startWorkedExam(page);
        const legacy=JSON.parse(store.getItem(KEY)); delete legacy.sessionId; legacy.v=1;
        const importedStore=readStore(); importedStore.setItem(KEY,JSON.stringify(legacy));
        const first=await open(importedStore,clock);
        assert.strictEqual(first.state().bannerHidden,false);
        importedStore.removeItem(KEY);
        const second=await open(importedStore,clock);
        assert.strictEqual(second.state().bannerHidden,false,'the imported DB is authoritative');
        await second.click('resumeBtn'); await second.choose(3);
        assert.strictEqual((await second.authoritative()).answers[4],3);
        await first.click('discardResumeBtn');
        assert.strictEqual((await second.authoritative()).answers[4],3,'stale v1 token cannot discard new owner');
        console.log('flow-ok');
    """)


def test_timer_write_and_answer_acceptance_do_not_erase_each_other():
    run_flow("""
        const {store,clock,page}=await context();
        await page.selectSeg('segCount',10); await page.click('startBtn');
        clock.value+=4000;
        const tick=page.tick(1); const selection=page.choose(3);
        await Promise.all([tick,selection]);
        assert.strictEqual(page.state().selectedChoice,'3');
        assert.strictEqual((await page.authoritative()).answers[0],3);
        await page.pagehide();
        const reopened=await open(store,clock); await reopened.click('resumeBtn');
        assert.strictEqual(reopened.state().answers[0],3);
        console.log('flow-ok');
    """)


def test_corrupt_authoritative_record_fails_closed_without_reimporting_valid_mirror():
    run_flow("""
        const {store,clock,page}=await context(); await startWorkedExam(page);
        const snapshot=page.checkpoint(); snapshot.answers[0]=9;
        const db=await new Promise((resolve,reject)=>{
          const r=page.context.indexedDB.open('exam-quiz-checkpoints',1);
          r.onsuccess=()=>resolve(r.result); r.onerror=()=>reject(r.error);
        });
        await new Promise((resolve,reject)=>{
          const tx=db.transaction('sessions','readwrite');
          tx.objectStore('sessions').put({format:1,revision:'corrupt-record',closed:false,snapshot},KEY);
          tx.oncomplete=resolve; tx.onabort=()=>reject(tx.error);
        });
        db.close();
        const reopened=await open(store,clock);
        assert.strictEqual(await reopened.authoritative(),null,'invalid DB answer must not reach the page');
        assert.strictEqual(reopened.state().bannerHidden,true);
        assert.strictEqual(store.getItem(KEY),null,'compatibility mirror cannot override a corrupt authoritative record');
        console.log('flow-ok');
    """)


def test_aborted_transactions_show_memory_only_state_instead_of_claiming_saved():
    run_flow("""
        const {IDBFactory}=require(path.join(ROOT,'tests','node_modules','fake-indexeddb'));
        const factory=new IDBFactory();
        const aborting={open(...args){
          const request=factory.open(...args);
          request.addEventListener('success',()=>{
            const db=request.result, native=db.transaction.bind(db);
            db.transaction=(...args)=>{const tx=native(...args);tx.abort();return tx;};
          });
          return request;
        }};
        const store=readStore(), clock={value:T0};
        const page=await createPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:store,clock,indexedDB:aborting});
        await page.click('startBtn'); await page.choose(3);
        assert.strictEqual(page.state().view,'exam','failed storage still allows in-memory practice');
        assert.strictEqual(page.state().selectedChoice,'3');
        assert.strictEqual(page.get('checkpointStatus').dataset.state,'unavailable');
        assert.ok(page.get('checkpointStatus').textContent.includes('無法回復'));
        assert.strictEqual(store.getItem(KEY),null,'aborted write cannot publish a saved mirror');
        const reopened=await createPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:store,clock,indexedDB:factory});
        assert.strictEqual(reopened.state().bannerHidden,true);
        assert.strictEqual(await reopened.authoritative(),null);
        console.log('flow-ok');
    """)


def test_failed_finish_does_not_acknowledge_completion_before_the_tombstone_commits():
    run_flow("""
        const {IDBFactory}=require(path.join(ROOT,'tests','node_modules','fake-indexeddb'));
        const factory=new IDBFactory(); let abortWrites=false;
        const controlled={open(...args){
          const request=factory.open(...args);
          request.addEventListener('success',()=>{
            const db=request.result, native=db.transaction.bind(db);
            db.transaction=(...args)=>{const tx=native(...args);if(abortWrites)tx.abort();return tx;};
          }); return request;
        }};
        const store=readStore(), clock={value:T0};
        const page=await createPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:store,clock,indexedDB:controlled});
        await page.click('startBtn'); await page.choose(3);
        abortWrites=true; await page.click('submitBtn');
        assert.strictEqual(page.state().view,'exam','no successful completion before clearing the durable session');
        assert.strictEqual(page.state().examDone,false);
        assert.ok(page.get('checkpointStatus').textContent.includes('交卷未完成'));
        const remaining=page.state().remain;
        await page.tick(2);
        assert.strictEqual(page.state().remain,remaining-2,'failed cleanup must not pause the original clock');
        abortWrites=false; await page.click('submitBtn');
        assert.strictEqual(page.state().view,'result','retry finishes after the tombstone commits');
        assert.strictEqual(await page.authoritative(),null);
        const reopened=await createPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:store,clock,indexedDB:factory});
        assert.strictEqual(reopened.state().bannerHidden,true);
        console.log('flow-ok');
    """)


def test_save_failure_cannot_make_finish_skip_an_existing_durable_record():
    run_flow("""
        const {IDBFactory}=require(path.join(ROOT,'tests','node_modules','fake-indexeddb'));
        const factory=new IDBFactory(); let abortWrites=false;
        const controlled={open(...args){
          const request=factory.open(...args);
          request.addEventListener('success',()=>{
            const db=request.result, native=db.transaction.bind(db);
            db.transaction=(...args)=>{const tx=native(...args);if(abortWrites)tx.abort();return tx;};
          }); return request;
        }};
        const store=readStore(), clock={value:T0};
        const page=await createPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:store,clock,indexedDB:controlled});
        await page.click('startBtn'); await page.choose(0);
        abortWrites=true; await page.choose(3);
        assert.strictEqual(page.state().selectedChoice,'3','memory-only selection is explicitly warned');
        assert.strictEqual(page.get('checkpointStatus').dataset.state,'unavailable');
        assert.strictEqual(JSON.parse(store.getItem(KEY)).answers[0],0,'last durable answer is still the original');
        await page.click('submitBtn');
        assert.strictEqual(page.state().view,'exam','save failure must not bypass the durable tombstone');
        assert.strictEqual(page.state().examDone,false);
        assert.ok(page.get('checkpointStatus').textContent.includes('交卷未完成'));
        abortWrites=false; await page.click('submitBtn');
        assert.strictEqual(page.state().view,'result');
        const reopened=await createPage({html:HTML,checkpointJs:CHECKPOINT_JS,storage:store,clock,indexedDB:factory});
        assert.strictEqual(await reopened.authoritative(),null,'retry closes the old committed snapshot');
        assert.strictEqual(reopened.state().bannerHidden,true);
        console.log('flow-ok');
    """)


def test_stale_resume_banner_tick_does_not_rebind_to_claimed_session_or_allow_discard():
    run_flow("""
        const {store,clock,page}=await context();
        await startWorkedExam(page);
        const originalState=JSON.parse(store.getItem(KEY));
        const originalSessionId=originalState.sessionId;

        // Two tabs both see the resume banner
        const a=await open(store,clock), b=await open(store,clock);
        assert.strictEqual(a.state().bannerHidden,false);
        assert.strictEqual(b.state().bannerHidden,false);

        // Tab A takes ownership and makes progress
        await a.click('resumeBtn');
        assert.strictEqual(a.state().view,'exam');
        await a.goto(2); await a.choose(3);
        const committed=await a.authoritative();
        assert.ok(committed);
        assert.notStrictEqual(committed.sessionId,originalSessionId,'tab A claimed a new session identity');
        const newSessionId=committed.sessionId;
        assert.strictEqual(committed.answers[2],3);

        // Tab B's resume banner timer ticks after Tab A has claimed the session
        await b.tick(1);

        // The banner must be hidden and pendingResume must not rebind to newSessionId
        assert.strictEqual(b.state().bannerHidden,true,'stale tab banner must be hidden once tick detects new owner');

        // Tab B clicking discard must not erase Tab A's active session
        await b.click('discardResumeBtn');
        const afterDiscard=await a.authoritative();
        assert.ok(afterDiscard,'discard from stale tab must not erase claimed session');
        assert.strictEqual(afterDiscard.sessionId,newSessionId);
        assert.strictEqual(afterDiscard.answers[2],3);

        // Tab B clicking resume must not hijack Tab A's active session
        await b.click('resumeBtn');
        const afterResume=await a.authoritative();
        assert.ok(afterResume,'resume from stale tab must not hijack claimed session');
        assert.strictEqual(afterResume.sessionId,newSessionId);
        assert.strictEqual(afterResume.answers[2],3);
        assert.strictEqual(b.state().view,'setup','stale tab must stay on setup view');

        console.log('flow-ok');
    """)


def test_stale_legacy_resume_banner_tick_does_not_rebind_or_clear_upgraded_session():
    run_flow("""
        const {store,clock,page}=await context();
        await startWorkedExam(page);
        const legacy=JSON.parse(store.getItem(KEY)); delete legacy.sessionId; legacy.v=1;
        const legacyStore=readStore(); legacyStore.setItem(KEY,JSON.stringify(legacy));

        const a=await open(legacyStore,clock), b=await open(legacyStore,clock);
        assert.strictEqual(a.state().bannerHidden,false);
        assert.strictEqual(b.state().bannerHidden,false);

        // Tab A resumes the legacy checkpoint and gets upgraded session ID
        await a.click('resumeBtn');
        await a.goto(2); await a.choose(3);
        const committed=await a.authoritative();
        assert.ok(committed);
        assert.strictEqual(typeof committed.sessionId,'string');
        const upgradedSessionId=committed.sessionId;
        assert.strictEqual(committed.answers[2],3);

        // Tab B ticks after Tab A has claimed and upgraded the session
        await b.tick(1);
        assert.strictEqual(b.state().bannerHidden,true,'stale tab banner must be hidden once tick detects upgrade');

        // Tab B clicking discard must not erase upgraded session
        await b.click('discardResumeBtn');
        const afterDiscard=await a.authoritative();
        assert.ok(afterDiscard,'discard from stale tab must not erase upgraded session');
        assert.strictEqual(afterDiscard.sessionId,upgradedSessionId);
        assert.strictEqual(afterDiscard.answers[2],3);

        // Tab B clicking resume must not hijack upgraded session
        await b.click('resumeBtn');
        const afterResume=await a.authoritative();
        assert.ok(afterResume,'resume from stale tab must not hijack upgraded session');
        assert.strictEqual(afterResume.sessionId,upgradedSessionId);
        assert.strictEqual(afterResume.answers[2],3);
        assert.strictEqual(b.state().view,'setup');

        console.log('flow-ok');
    """)
