import copy
import json
import unittest
from tests import test_study as fixtures
from polimi_lectures.study import Study
from polimi_lectures.study_course import pack

@unittest.skipIf(fixtures.pymupdf is None,'Requires native slides runtime')
class PreparationTest(unittest.TestCase):
    setUp=fixtures.StudyTest.setUp
    tearDown=fixtures.StudyTest.tearDown

    def start(self):
        held=next(d['id'] for d in self.store.course_inventory(self.course)['documents'] if d['title']=='PC-1st-part-25-07-21.pdf')
        p=self.store.course_create(self.course,'Primo parziale: PRAM',reserved=[held]);self.path=p['id'];self.sid=p['sid']
        task=self.task();self.commit(task,{'summary':'Primo parziale PRAM','included':['PRAM'],'excluded':['Secondo parziale'],'clarification':None})
        self.store.course_confirm(self.path)
        return self.path

    def task(self):return self.store.course_task(self.path)
    def commit(self,task,result):
        self.store.preparation_begin(self.path,task)
        return self.store.preparation_commit(self.path,task,result)

    def read(self,task):
        refs=[s['id'] for s in task['sources']]
        return self.commit(task,{'evidence':[{'concept':'PRAM','statement':'PRAM distingue letture e scritture concorrenti.','sources':refs[:1]}],'questions':[{'text':'What is the difference between EREW, CREW, and CRCW models? Provide an example for each of them. (1)','format':'open','in_scope':True,'skills':['PRAM'],'sources':refs[:1]}] if task['kind']=='exam_reading' else []})

    def blueprint(self):
        refs=[c['sources'][0] for c in self.store.preparation_evidence(self.path)]
        docs=[r[0] for r in self.store.db.execute("SELECT DISTINCT p.document FROM prep_spans s JOIN passages p ON p.id=s.source WHERE s.path=? AND s.status!='outside'",(self.path,))]
        return {'chapters':[{'id':'pram','title':'PRAM dalle basi','objective':'Spiegare il modello','prerequisites':[],'sources':refs[:2],'priority':'alta','priority_reason':'Programma e tema autentico','assessment':'Domanda aperta motivata','coverage':docs}], 'gaps':[],'outside_scope':[],'coverage_notes':'Evidenze collegate','objective_coverage':[{'index':0,'chapters':['pram']}]}

    def to_chapter(self):
        self.start()
        for _ in range(30):
            task=self.task()
            if task['kind']=='chapter':return task
            if task['kind'] in ('exam_reading','evidence_reading'):self.read(task)
            elif task['kind']=='selection':self.commit(task,{'decisions':[{'source':r['id'],'status':'relevant','reason':'PRAM nel testo','skills':['PRAM']} for r in task['previews']]})
            elif task['kind']=='map':self.commit(task,self.blueprint())
            elif task['kind']=='map_review':self.commit(task,{'summary':'Mappa coerente','checked_objectives':[0],'issues':[]})
            else:self.fail(task['kind'])
        self.fail('Preparation did not reach chapter')

    def content(self):
        ref=self.store.preparation_evidence(self.path)[0]['sources'][0]
        return {'blocks':[{'id':'intro','kind':'text','text':'PRAM è un modello astratto.','sources':[ref]},{'id':'exercise','kind':'activity','depends_on':['intro'],'spec':{'kind':'numeric','title':'Riduzione','prompt':'Otto valori: quanti livelli?','answer':3,'origin':'generated','assumptions':'Riduzione binaria','solution':'Tre livelli','rubric':'Conta i livelli','sources':[ref],'verification':{'model':'reduction_depth','input':{'n':8},'expected':3}}}]}

    def review(self,task,blocking=False):
        return {'summary':'Revisione completa','checked_blocks':[b['id'] for b in task['draft']['blocks']],'checked_sources':list({r for b in task['draft']['blocks'] for r in b.get('sources',b.get('spec',{}).get('sources',[]))}),'issues':[{'block':'intro','severity':'blocking','message':'Definizione da chiarire','sources':self.content()['blocks'][0]['sources']}] if blocking else []}

    def test_full_pipeline_exams_first_and_two_complete_reviews_before_publish(self):
        chapter=self.to_chapter();content=self.content();self.commit(chapter,content)
        self.assertIsNone(self.store._chapter(self.path,'pram'))
        task=self.task();self.assertEqual(task['kind'],'review_solve')
        self.assertNotIn('answer',task['draft']['blocks'][1]['spec']);self.assertNotIn('solution',task['draft']['blocks'][1]['spec']);self.assertNotIn('verification',task['draft']['blocks'][1]['spec'])
        self.commit(task,{'solutions':[{'block':'exercise','answer':3,'reasoning':'Tre livelli'}]})
        for phase in ['review_discipline','review_didactic']:
            task=self.task();self.assertEqual(task['kind'],phase);self.commit(task,self.review(task));self.assertIsNone(self.store._chapter(self.path,'pram'))
        task=self.task();self.assertEqual(task['kind'],'publish');self.commit(task,{})
        self.assertEqual(self.store._chapter(self.path,'pram')['content']['review']['status'],'reviewed')
        self.store.course_select(self.sid,'pram')
        public=self.store.view(self.sid)['activities'][0]['spec']
        self.assertNotIn('verification',public);self.assertNotIn('answer',public)
        self.assertEqual(self.task()['kind'],'done')

    def test_actual_exam_profile_excludes_classroom_and_generated_questions(self):
        self.start();task=self.task();self.assertEqual(task['kind'],'exam_reading');self.read(task)
        self.assertEqual(self.store.course_exam_profile(self.path)['total'],1)
        self.store.db.execute('INSERT INTO course_questions VALUES(?,?,?,?)',(self.path,'classroom',task['document'],pack({'origin':'classroom','authenticity_verified':False,'text':'Domanda orale','format':'choice','skills':['PRAM'],'sources':[task['sources'][0]['id']],'in_scope':True})));self.store.db.commit()
        self.assertEqual(self.store.course_exam_profile(self.path)['total'],1)

    def test_tool_read_receipts_admit_only_sources_actually_read(self):
        self.start();task=self.task();self.store.preparation_begin(self.path,task)
        other=self.store.db.execute("SELECT p.id FROM passages p WHERE p.course=? AND p.kind='video'",(self.course,)).fetchone()[0]
        with self.assertRaisesRegex(ValueError,'non letta'):self.store._prep_refs(self.path,task,[other])
        self.store.preparation_read(task['task_id'],self.store.source(other),'read_source')
        self.assertEqual(self.store._prep_refs(self.path,task,[other]),[other])

    def test_archive_restart_retains_history_but_imports_no_generated_content(self):
        self.to_chapter();old=self.path
        fresh=self.store.preparation_restart(old)
        self.assertTrue(self.store._path(old)['objective']['archived']);self.assertEqual(fresh['objective']['request'],'Primo parziale: PRAM')
        self.assertNotIn('summary',fresh['objective']);self.assertFalse(self.store.preparation_evidence(fresh['id']));self.assertIsNone(fresh['plan'])
        self.assertTrue(self.store.preparation_evidence(old));self.assertEqual(self.store.course_task(fresh['id'])['kind'],'scope')
        with self.assertRaisesRegex(ValueError,'archiviata'):self.store.course_task(old)

    def test_incomplete_review_or_wrong_numeric_result_cannot_publish(self):
        chapter=self.to_chapter();content=self.content();content['blocks'][1]['spec']['answer']=4
        with self.assertRaisesRegex(ValueError,'Risposta numerica'):self.commit(chapter,content)
        content['blocks'][1]['spec']['answer']=3;self.commit(chapter,content)
        task=self.task();self.commit(task,{'solutions':[{'block':'exercise','answer':3,'reasoning':'Tre livelli binari'}]})
        task=self.task();bad=self.review(task);bad['checked_blocks']=[]
        with self.assertRaisesRegex(ValueError,'tutti i blocchi'):self.commit(task,bad)
        self.assertIsNone(self.store._chapter(self.path,'pram'))

    def test_restart_reuses_new_engine_checkpoints_not_legacy_cards(self):
        self.start();task=self.task();self.read(task)
        before=self.store.preparation_evidence(self.path)
        other=Study(self.root)
        self.assertEqual(other.preparation_evidence(self.path),before);self.assertNotEqual(other.course_task(self.path)['kind'],'exam_reading');other.db.close()

    def test_stale_source_cannot_commit(self):
        self.start();task=self.task();self.store.preparation_begin(self.path,task)
        self.store.db.execute('UPDATE documents SET fingerprint=? WHERE id=?',('changed',task['document']));self.store.db.commit()
        with self.assertRaisesRegex(ValueError,'Fonte cambiata'):self.store.preparation_commit(self.path,task,{'evidence':[]})

    def test_header_similarity_does_not_reserve_a_different_paper(self):
        self.start()
        training=next(d for d in self.store.course_inventory(self.course)['documents'] if d['title']=='PC-1st-part-25-06-19.pdf')
        self.assertFalse(training['reserved'])

    def test_selection_is_reversible_and_uncertain_sources_are_read(self):
        self.start();self.read(self.task());task=self.task();self.assertEqual(task['kind'],'selection')
        self.commit(task,{'decisions':[{'source':p['id'],'status':'uncertain','reason':'Serve lettura completa'} for p in task['previews']]})
        pending=self.task()
        while pending['kind']=='selection':
            self.commit(pending,{'decisions':[{'source':p['id'],'status':'outside','reason':'Argomento escluso'} for p in pending['previews']]});pending=self.task()
        self.assertEqual(pending['kind'],'evidence_reading')
        source=pending['sources'][0]['id'];self.store.preparation_decide(self.path,source,'outside','Scelta esplicita')
        self.assertEqual(next(d for d in self.store.preparation_decisions(self.path) if d['source']==source)['status'],'outside')

    def test_large_unit_continues_from_exact_character_checkpoint(self):
        self.start();task=self.task()
        ref=task['sources'][0]['id'];text=('A long coherent paragraph about PRAM and processor access rules.\n\n'*700)
        with self.store.db:self.store.db.execute('UPDATE passages SET text=? WHERE id=?',(text,ref))
        self.store.course_sync(self.path)
        small=self.store.course_task(self.path,input_tokens=1000)
        self.assertEqual(small['sources'][0]['start_char'],0);self.assertLess(small['sources'][0]['end_char'],len(text))
        self.commit(small,{'evidence':[{'concept':'PRAM','statement':'Lettura parziale','sources':[ref]}],'questions':[]})
        later=self.store.course_task(self.path,input_tokens=1000)
        self.assertEqual(later['sources'][0]['id'],ref);self.assertEqual(later['sources'][0]['start_char'],small['sources'][0]['end_char'])

    def test_partial_overlap_hides_only_that_question_and_never_leaks_context_or_pdf(self):
        import pymupdf
        material=self.root/'corsi'/self.course/'materiali'
        shared='Describe the exclusive read exclusive write PRAM model and explain how simultaneous processor accesses to a single memory cell are handled by this model.'
        unique='Explain the independent memory bandwidth exercise in this second question with a new architecture and a new set of parameters that does not appear elsewhere.'
        for name,text in [('exam-held.pdf','Parallel Computing\nExercise 1\n'+shared),('exam-other.pdf','Parallel Computing\nExercise 1\n'+shared+'\nExercise 2\n'+unique)]:
            d=pymupdf.open();page=d.new_page();page.insert_textbox(pymupdf.Rect(30,30,550,780),text);d.save(material/name);d.close()
        self.store.import_course(self.course);docs=self.store.course_inventory(self.course)['documents'];held=next(d['id'] for d in docs if d['title']=='exam-held.pdf');other=next(d['id'] for d in docs if d['title']=='exam-other.pdf')
        self.store._reserve(self.course,[held]);ref=self.store.db.execute('SELECT id FROM passages WHERE document=?',(other,)).fetchone()[0]
        source=self.store.source(ref);self.assertTrue(source['redacted']);self.assertNotIn(shared,source['text']);self.assertIn(unique,' '.join(source['text'].split()))
        with self.assertRaisesRegex(ValueError,'riservati'):self.store.render_pdf(ref)
        for row in self.store.search(self.course,'exclusive processor'):
            self.assertNotIn(shared,row['text']);self.assertNotIn(shared,json.dumps(row.get('context',[])))
        read=self.store.read_material(self.sid,other,1,100);self.assertNotIn(shared,json.dumps(read));self.assertIn(unique,' '.join(' '.join(line['text'] for line in read['lines']).split()))
        grep=self.store.grep_materials(self.sid,'Describe the exclusive',other);self.assertFalse(grep)

    def test_alias_resolves_linked_material_without_using_legacy_identifier_as_citation(self):
        source=self.store.db.execute("SELECT id,document FROM passages WHERE title='lecture.pdf'",()).fetchone()
        with self.store.db:self.store.db.execute('INSERT INTO source_aliases VALUES(?,?,?)',(self.course,'old-alignment-id',source['document']))
        result=self.store.read_material(self.sid,'old-alignment-id')
        self.assertEqual(result['document'],source['document']);self.assertIn(source['id'],[line['source'] for line in result['lines']])

    def test_persistent_blocker_suspends_its_dependents_and_student_can_reopen_review(self):
        chapter=self.to_chapter();self.commit(chapter,self.content())
        for _ in range(20):
            task=self.task()
            if task['kind']=='done':break
            if task['kind']=='review_solve':self.commit(task,{'solutions':[{'block':'exercise','answer':3,'reasoning':'Tre livelli binari'}]})
            elif task['kind'].startswith('review_'):self.commit(task,self.review(task,blocking=True))
            elif task['kind']=='repair_chapter':self.commit(task,self.content())
            elif task['kind']=='publish':self.commit(task,{})
            else:self.fail(task['kind'])
        current=self.store._chapter(self.path,'pram')['content']
        self.assertEqual(set(current['review']['blocked_blocks']),{'intro','exercise'})
        self.assertTrue(all(b.get('suspended') for b in current['blocks']))
        issue=self.store.preparation_progress(self.path)['issues'][0]
        self.store.preparation_issue(self.path,issue['id'],'Il docente ha chiarito il punto in questa pagina.')
        self.assertEqual(self.task()['kind'],'repair_chapter')

    def test_checkpoint_idempotence_rejects_conflicting_results(self):
        self.start();task=self.task()
        result={'evidence':[{'concept':'PRAM','statement':'Modello astratto','sources':[task['sources'][0]['id']]}],'questions':[]}
        self.commit(task,result);self.store.preparation_commit(self.path,task,result)
        with self.assertRaisesRegex(ValueError,'differente'):self.store.preparation_commit(self.path,task,dict(result,questions=[{'text':'Different'}]))

    def test_notebook_links_resolve_only_listed_cells_and_legacy_file_id(self):
        notebook=self.store.db.execute("SELECT id,path FROM documents WHERE path LIKE '%test.ipynb'").fetchone()
        with self.store.db:
            self.store.db.execute('INSERT INTO passages(id,document,course,kind,title,path,page,text,quality,reserved,solution,metadata) VALUES(?,?,?,?,?,?,?,?,?,0,0,?)',('extra-cell',notebook['id'],self.course,'notebook','test.ipynb',notebook['path'],1,'Unrelated cell','originale','{}'))
            self.store.db.execute('INSERT INTO documents VALUES(?,?,?,?,NULL)',('alignment-document',self.course,'corsi/'+self.course+'/lesson/allineamento/allineamento.json','alignment-fingerprint'))
            metadata={'alignment':{'material':{'kind':'notebook','file_id':'old-notebook-id','file':'test.ipynb','cells':[{'cell_index':0}]},'status':'candidate','confidence':'medium'}}
            self.store.db.execute('INSERT INTO passages(id,document,course,kind,title,path,start,end,text,quality,reserved,solution,metadata) VALUES(?,?,?,?,?,?,?,?,?,?,0,0,?)',('alignment-source','alignment-document',self.course,'alignment','allineamento.json','corsi/'+self.course+'/lesson/allineamento/allineamento.json',0,10,'x=1','medium',pack(metadata)))
        self.store.preparation_catalog(self.course)
        links=self.store.db.execute('SELECT target FROM source_links WHERE source=?',('alignment-source',)).fetchall()
        self.assertEqual(len(links),1);self.assertNotEqual(links[0][0],'extra-cell')
        self.assertEqual(self.store._resolve_document(self.course,'old-notebook-id'),notebook['id'])

    def test_external_claim_requires_read_url_and_notation_comparison(self):
        self.start();task=self.task();self.store.preparation_begin(self.path,task)
        claim={'concept':'PRAM','statement':'Confronto della notazione','sources':[task['sources'][0]['id']],'provenance':'external','external_sources':['https://example.edu/reference'],'notation_comparison':'Stesse ipotesi e simboli dichiarati.'}
        with self.assertRaisesRegex(ValueError,'web non letta'):self.store.preparation_commit(self.path,task,{'evidence':[claim],'questions':[]})
        self.store.preparation_read(task['task_id'],{'url':'https://example.edu/reference','text':'Original reference with explicit assumptions'},'read_web_page')
        self.store.preparation_commit(self.path,task,{'evidence':[claim],'questions':[]})
        self.assertEqual(self.store.preparation_evidence(self.path)[0]['provenance'],'external')

    def test_task_recovery_marks_inflight_without_losing_completed_evidence(self):
        self.start();self.read(self.task());task=self.task();self.store.preparation_begin(self.path,task)
        self.store.preparation_metric(self.path,task['task_id'],'waiting',metrics={'estimated_input_tokens':1234})
        self.store.preparation_recover()
        state=self.store.db.execute('SELECT state FROM prep_tasks WHERE id=?',(task['task_id'],)).fetchone()[0]
        self.assertEqual(state,'paused');self.assertTrue(self.store.preparation_evidence(self.path))

    def test_unlock_never_removes_reservations_from_another_active_goal(self):
        self.start();held=self.store._path(self.path)['objective']['reserved_requested'][0]
        other=self.store.course_create(self.course,'Altro obiettivo del primo parziale',reserved=[held])
        self.store.course_unlock(self.path,held)
        self.assertTrue(self.store.db.execute('SELECT reserved FROM passages WHERE document=?',(held,)).fetchone()[0])
        self.assertIn(held,self.store._path(other['id'])['objective']['reserved_requested'])
        self.store.course_unlock(other['id'],held)
        self.assertFalse(self.store.db.execute('SELECT reserved FROM passages WHERE document=?',(held,)).fetchone()[0])
