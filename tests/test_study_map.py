import copy,json,unittest
from unittest.mock import patch
from tests import test_study as fixtures
from tests import test_study_preparation as prep
from polimi_lectures.study import Study
from polimi_lectures.study_course import pack
from polimi_lectures.study_map import STRATEGY,compact_fact,recover_map_fields

@unittest.skipIf(fixtures.pymupdf is None,'Requires native runtime')
class MapTest(unittest.TestCase):
    setUp=fixtures.StudyTest.setUp
    tearDown=fixtures.StudyTest.tearDown
    task=prep.PreparationTest.task
    commit=prep.PreparationTest.commit
    read=prep.PreparationTest.read
    blueprint=prep.PreparationTest.blueprint

    def start(self,strategy=STRATEGY):return prep.PreparationTest.start(self,map_strategy=strategy)
    def until_map(self,strategy=STRATEGY):
        self.start(strategy)
        for _ in range(30):
            task=self.task()
            if task['kind'] in ('map_outline','map'):return task
            if task['kind']=='selection':self.commit(task,{'decisions':[{'source':s['id'],'status':'relevant','reason':'PRAM','skills':['PRAM']} for s in task['previews']]})
            else:self.read(task)
        self.fail('Planner not reached')
    def outline(self):
        task=self.until_map();self.assertEqual(task['kind'],'map_outline')
        result=self.blueprint();result['chapters'][0]['sources']=[]
        self.commit(task,result);return self.task()
    def part(self,task):return {'additions':[{'chapter':'pram','evidence':task['evidence_ids'],'notes':'Insegna PRAM dalle basi; conserva le ipotesi di accesso.','skills':['PRAM']}]}

    def test_projection_keeps_all_teaching_fields_without_copying_raw_excerpts(self):
        claim={'id':'a','concept':'PRAM','statement':'Fatto attestato','notation':['p'],'assumptions':['Unit cost'],'issues':['Ambiguita'],'examples':['Example'],'sources':['ref'],'provenance':'course','read_ranges':[{'excerpt':'RAW_EXCERPT'*10000}],'access_fingerprints':{'ref':'hash'},'dependencies':{'doc':'hash'}}
        projected=compact_fact(claim)
        for key in ('id','statement','notation','assumptions','issues','examples','sources','provenance'):self.assertEqual(projected[key],claim[key])
        self.assertNotIn('read_ranges',projected);self.assertNotIn('RAW_EXCERPT',pack(projected));self.assertIn('read_ranges',claim)

    def test_contributions_then_single_reconciliation_and_scoped_review_context(self):
        task=self.outline();self.assertEqual(task['kind'],'map_contribution')
        self.assertNotIn('previous',task);self.assertNotIn('read_ranges',pack(task['evidence']))
        self.assertIsNone(self.store._plan(self.path))
        result=self.part(task);self.commit(task,result);self.store.preparation_commit(self.path,task,result)
        final=self.task();self.assertEqual(final['kind'],'map');self.assertTrue(final['final_batch']);self.assertNotIn('evidence',final)
        plan=self.blueprint();plan['chapters'][0]['sources']=[]
        self.commit(final,plan);saved=self.store._plan(self.path);self.assertTrue(saved['data']['final'])
        expected={ref for c in self.store.preparation_evidence(self.path,limit=100000) for ref in c['sources']}
        self.assertEqual(set(saved['data']['chapters'][0]['sources']),expected)
        self.store.preparation_commit(self.path,final,plan);self.assertEqual(self.store._plan(self.path)['version'],saved['version'])
        review=self.task();self.assertEqual(review['kind'],'map_review');self.assertNotIn('evidence',review);self.assertIn('evidence_context',review)
        self.commit(review,{'summary':'Copertura controllata','checked_objectives':[0],'issues':[]})
        chapter=self.task();self.assertEqual(chapter['kind'],'chapter');self.assertNotIn('evidence',chapter);self.assertIn('evidence_context',chapter)
        facts=self.store.preparation_facts(self.path,chapter='pram',limit=1);self.assertEqual(len(facts['evidence']),1);self.assertIsNotNone(facts['next_offset'])
        self.assertNotIn('read_ranges',pack(facts))

    def test_truncated_map_recovers_only_complete_fields_and_cannot_rewrite_them(self):
        task=self.outline();self.commit(task,self.part(task));final=self.task()
        plan=self.blueprint();raw=json.dumps({'chapters':plan['chapters'],'gaps':['Keep this uncertainty']})[:-1]+',"outside_scope":[{"document":"cut'
        recovered=recover_map_fields(raw)
        self.assertEqual(recovered['chapters'],plan['chapters']);self.assertEqual(recovered['gaps'],['Keep this uncertainty']);self.assertNotIn('outside_scope',recovered)
        self.assertIsNone(recover_map_fields('{"chapters":[{"id":"cut'))
        final['recovery']={'call':'saved-call','fields':recovered}
        result={k:v for k,v in plan.items() if k not in ('chapters','gaps')}
        merged=self.store._map_merge(self.path,final,result)
        self.assertEqual(merged['chapters'][0]['objective'],plan['chapters'][0]['objective']);self.assertIn('Keep this uncertainty',merged['gaps'])
        with self.assertRaisesRegex(ValueError,'campi mancanti'):self.store._map_merge(self.path,final,plan)

    def test_reconciliation_is_bounded_and_preserves_previous_caveats(self):
        task=self.outline();self.commit(task,self.part(task));final=self.task()
        self.assertEqual(final['reconciliation_version'],2)
        result=self.blueprint();result['chapters'][0]['sources']=[]
        final['previous_notes']={'gaps':['Original unresolved uncertainty'],'outside_scope':[]}
        merged=self.store._map_merge(self.path,final,result)
        self.assertIn('Original unresolved uncertainty',merged['gaps'])
        huge=copy.deepcopy(result);huge['coverage_notes']='x'*24001
        with self.assertRaisesRegex(ValueError,'24000'):self.store._map_merge(self.path,final,huge)

    def test_successful_mapping_prevents_reapplying_old_truncated_draft(self):
        task=self.outline();self.commit(task,self.part(task));failed=self.task()
        with self.store.db:
            self.store.db.execute("UPDATE prep_tasks SET state='error' WHERE id=?",(failed['task_id'],))
            self.store.db.execute('INSERT INTO prep_model_calls VALUES(?,?,?,?,?,?,?)',('truncated-call',self.path,failed['task_id'],'{}','preparation',pack({'output':json.dumps(self.blueprint())[:-1]+',"unfinished":'}),'now'))
        claims=self.store.preparation_evidence(self.path,limit=100000)
        self.assertIsNotNone(self.store._map_recovery(self.path,failed['build'],claims))
        different={k:v for k,v in failed.items() if k not in ('task_id','engine','objective','source_revisions')};different['reconciliation_version']=99
        succeeded=self.store._prep_task(self.path,different);self.commit(succeeded,self.blueprint())
        self.assertIsNone(self.store._map_recovery(self.path,failed['build'],claims))

    def reviewed_map_with_problem(self):
        task=self.outline();self.commit(task,self.part(task));final=self.task()
        plan=self.blueprint();plan['gaps']=['Historical partial map','Actual unresolved formula']
        doc=self.store.source(plan['chapters'][0]['sources'][0])['document']
        plan['outside_scope']=[{'document':doc,'reason':'Old incorrect exclusion'}]
        self.commit(final,plan);review=self.task();ref=plan['chapters'][0]['sources'][0]
        self.store.preparation_begin(self.path,review);self.store.preparation_read(review['task_id'],self.store.source(ref),'read_source')
        self.commit(review,{'summary':'Correct stale exclusion and attach source','checked_objectives':[0],'checked_sources':[ref],'issues':[{'block':'map','severity':'blocking','message':'Stale exclusion','sources':[ref]}]})
        repair=self.task();self.assertEqual(repair.get('repair_version'),1);return repair,ref,doc

    def test_review_repairs_revoke_stale_metadata_and_preserve_history_and_sources(self):
        task,ref,doc=self.reviewed_map_with_problem();version=self.store._plan(self.path)['version']
        old_claims=self.store.preparation_evidence(self.path,limit=100000)
        actual_doc=self.store.source(ref)['document']
        # Revoke the actual document with evidence from that document.
        if actual_doc!=doc:
            ref=next(s['id'] for s in task['repair_sources'] if s['document']==doc)
        result={'chapter_updates':[{'id':'pram','assessment':'Motivate without importing excluded task graphs.','sources':[ref]}],
          'resolve_gaps':[{'index':0,'reason':'Full map now reconciled','sources':[]}],
          'revoke_exclusions':[{'document':doc,'reason':'Reviewed original establishes prerequisite','sources':[ref]}],
          'scope_updates':[{'source':ref,'status':'prerequisite','reason':'Original read in expert review'}]}
        self.commit(task,result);saved=self.store._plan(self.path)
        self.assertGreater(saved['version'],version);self.assertEqual(saved['data']['gaps'],['Actual unresolved formula'])
        self.assertEqual(saved['data']['outside_scope'],[]);self.assertEqual(saved['data']['gap_history'][0]['state'],'superseded')
        self.assertEqual(saved['data']['scope_history'][0]['state'],'revoked')
        self.assertIn(ref,saved['data']['chapters'][0]['sources']);self.assertIn(doc,saved['data']['chapters'][0]['coverage'])
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM prep_scope_changes').fetchone()[0],1)
        self.assertEqual(self.store.preparation_evidence(self.path,limit=100000),old_claims)
        self.assertEqual(self.task()['kind'],'map_review')
        self.store.preparation_commit(self.path,task,result)
        self.assertEqual(self.store.db.execute('SELECT count(*) FROM prep_scope_changes').fetchone()[0],1)

    def test_invalid_or_stale_repair_cannot_change_scope_or_other_chapters(self):
        task,ref,doc=self.reviewed_map_with_problem();before=self.store._plan(self.path)
        for result in [{'chapter_updates':[{'id':'alien','sources':[ref]}]},
                       {'chapter_updates':[{'id':'pram','sources':['unknown-ref']}]},
                       {'revoke_exclusions':[{'document':doc,'reason':'Unsupported','sources':[]}]},
                       {'resolve_gaps':[{'index':999,'reason':'Invalid'}]},
                       {'scope_updates':[{'source':ref,'status':'outside','reason':'Not a bounded repair'}]},
                       {'chapters':[]}]:
            with self.assertRaises(ValueError):self.commit(task,result)
            self.assertEqual(self.store._plan(self.path),before)
            self.assertEqual(self.store.db.execute('SELECT count(*) FROM prep_scope_changes').fetchone()[0],0)
        # A previously repaired version must never be overwritten by a stale delta.
        self.commit(task,{'chapter_updates':[{'id':'pram','objective':'Updated objective'}]})
        with self.assertRaisesRegex(ValueError,'obsoleta'):self.store._map_apply_repair(self.path,task,{})

    def test_missing_or_foreign_evidence_and_wrong_chapter_cannot_be_committed(self):
        task=self.outline();valid=self.part(task)
        for alter in ('missing','foreign','chapter'):
            bad=copy.deepcopy(valid)
            if alter=='missing':bad['additions'][0]['evidence']=task['evidence_ids'][:-1]
            elif alter=='foreign':bad['additions'][0]['evidence'].append('another-course-fact')
            else:bad['additions'][0]['chapter']='not-in-outline'
            with self.assertRaises(ValueError):self.commit(task,bad)
            self.assertEqual(self.store.db.execute('SELECT count(*) FROM prep_map_parts').fetchone()[0],0)
        self.commit(task,valid)

    def test_parts_survive_restart_and_changed_objective_rejects_old_tasks(self):
        task=self.outline();result=self.part(task)
        old=self.store._path(self.path)['objective'];changed=dict(old,included=old['included']+['New objective'])
        with self.store.db:self.store.db.execute('UPDATE course_paths SET objective=? WHERE id=?',(pack(changed),self.path))
        with self.assertRaisesRegex(ValueError,'obsoleto'):self.commit(task,result)
        with self.store.db:self.store.db.execute('UPDATE course_paths SET objective=? WHERE id=?',(pack(old),self.path))
        self.commit(task,result)
        other=Study(self.root)
        try:
            following=other.course_task(self.path);self.assertEqual(following['kind'],'map')
            self.assertEqual(other.db.execute('SELECT count(*) FROM prep_map_parts').fetchone()[0],1)
        finally:other.db.close()

    def test_migration_reuses_only_matching_completed_evidence_of_current_path(self):
        task=self.until_map(strategy='legacy');first=copy.deepcopy(task)
        first['evidence']=first['evidence'][:1];first['final_batch']=False
        first=self.store._prep_task(self.path,{k:v for k,v in first.items() if k not in ('task_id','engine','objective')})
        self.commit(first,self.blueprint());old_plan=self.store._plan(self.path)
        self.store.course_status(self.path,'paused');self.store.preparation_optimize_map(self.path)
        following=self.task();self.assertEqual(following['kind'],'map_contribution');self.assertEqual(following['covered'],1)
        self.assertNotIn(first['evidence'][0]['id'],following['evidence_ids'])
        self.assertEqual(self.store._plan(self.path),old_plan)
        self.assertEqual(self.store.db.execute('SELECT state FROM prep_tasks WHERE id=?',(first['task_id'],)).fetchone()[0],'done')

    def test_protected_or_unknown_evidence_never_enters_retrieval(self):
        task=self.outline();facts=self.store.preparation_facts(self.path)
        self.assertNotIn('Reserved unique',pack(facts))
        with self.assertRaises(ValueError):self.store.preparation_facts(self.path,ids=['unknown-fact'])
        ids=[c['id'] for c in task['evidence']]
        subset=self.store.preparation_facts(self.path,ids=ids[:1]);self.assertEqual([c['id'] for c in subset['evidence']],ids[:1])

    def test_peek_is_reused_without_rescanning_but_database_changes_invalidate_it(self):
        self.outline()
        with patch.object(self.store,'course_sync',wraps=self.store.course_sync) as sync:
            peek=self.store.course_peek_task(self.path,model_key='model-before-routing')
            task=self.store.course_task(self.path,model_key='model-after-routing')
            self.assertEqual(sync.call_count,1)
            self.assertEqual(task['evidence_ids'],peek['evidence_ids'])
            self.assertEqual(task['model_key'],'model-after-routing')
            self.store.course_peek_task(self.path,model_key='same')
            with self.store.db:self.store.db.execute('UPDATE course_paths SET updated=? WHERE id=?',('changed',self.path))
            self.store.course_task(self.path,model_key='same')
            self.assertEqual(sync.call_count,3)
