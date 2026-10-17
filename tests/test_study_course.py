import copy
import json
import unittest
from tests import test_study as fixtures
from polimi_lectures.study import Study

@unittest.skipIf(fixtures.pymupdf is None,'Requires native slides runtime')
class CourseTest(unittest.TestCase):
    setUp=fixtures.StudyTest.setUp
    tearDown=fixtures.StudyTest.tearDown

    def start(self):
        inv=self.store.course_inventory(self.course)
        held=next(d['id'] for d in inv['documents'] if d['title']=='PC-1st-part-25-07-21.pdf')
        self.path=self.store.course_create(self.course,engine=1,request='Primo parziale: PRAM e prefix sum',reserved=[held])['id']
        self.sid=self.store.course_path_view(self.path)['sid'];self.held=held
        task=self.store.course_task(self.path)
        self.store.course_commit(self.path,task,{'summary':'Primo parziale','included':['PRAM','prefix sum'],'excluded':['Secondo parziale'],'clarification':None})
        self.store.course_confirm(self.path)
        self.source=self.store.search(self.course,'exclusive')[0]['id']
        return self.path

    def blueprint(self):
        docs=[r[0] for r in self.store.db.execute('SELECT document FROM course_documents WHERE path=?',(self.path,))]
        return {'chapters':[{'id':'pram','title':'PRAM','objective':'Spiegare il modello e risolvere problemi','prerequisites':[],'sources':[self.source],'priority':'alta','priority_reason':'Presente nel programma e nei temi','assessment':'Domanda aperta e pseudocodice','exam_skills':['PRAM'],'coverage':docs}], 'gaps':['Trascrizione parziale'],'outside_scope':[],'coverage_notes':'Documenti letti per intero nei blocchi registrati.'}

    def read_all(self):
        while True:
            task=self.store.course_task(self.path)
            if task['kind']!='reading':break
            refs=[c['source'] for c in task['chunks']]
            self.store.course_commit(self.path,task,{'summary':'PRAM e accessi; spiegazione con fonti','topics':[{'title':'PRAM','sources':refs}],'sources':refs,'notation':['n'],'gaps':[],'questions':[{'text':'What is PRAM?','format':'open','in_scope':True,'skills':['PRAM'],'sources':refs,'points':1}] if task['exam'] else []})
        while True:
            task=self.store.course_task(self.path)
            if task['kind']!='integrate':break
            self.store.course_commit(self.path,task,self.blueprint())
        task=self.store.course_task(self.path);self.assertEqual(task['kind'],'reconcile')
        self.store.course_commit(self.path,task,self.blueprint())

    def content(self):
        return {'blocks':[{'id':'intro','kind':'text','text':'PRAM è un modello astratto. [Fonte](source:'+self.source+').','sources':[self.source]},
          {'id':'practice','kind':'activity','spec':{'kind':'numeric','title':'Una riduzione','prompt':'Due processori, due valori: quanti livelli?','answer':1,'solution':'Un livello.','rubric':'Modello e numero di livelli','assumptions':'Somma unitaria e due processori','origin':'generated','sources':[self.source]}}]}

    def prepare(self):
        self.start();self.read_all();task=self.store.course_task(self.path)
        self.assertEqual(task['kind'],'chapter');self.store.course_commit(self.path,task,self.content())
        self.store.course_select(self.sid,'pram')

    def test_no_holdouts_are_preselected_without_an_objective(self):
        self.assertEqual(self.store.course_inventory(self.course)['proposed'],[])
        path=self.store.course_create(self.course,engine=1,request='Primo parziale: PRAM')['id']
        self.assertEqual(self.store.course_path_view(path)['objective']['reserved'],[])

    def test_reservation_candidates_match_the_requested_partial(self):
        from polimi_lectures.study_course import exam_type
        self.assertEqual(exam_type('primo parziale'),'part:1')
        self.assertEqual(exam_type('PC-2nd-part-25-06-19.pdf'),'part:2')
        self.assertEqual(exam_type('esame completo'),'full')
        self.assertIsNone(exam_type('exam-2025.pdf'))
        held=next(d['id'] for d in self.store.course_inventory(self.course)['documents'] if d['exam'])
        with self.store.db:
            self.store.db.execute("UPDATE documents SET path='Exams/PC-2nd-part-25-06-19.pdf' WHERE id=?",(held,))
        self.assertEqual(self.store._reservation_candidates(self.course,{'request':'esame completo'}),[])
        path=self.store.course_create(self.course,engine=1,request='Primo parziale: PRAM')['id']
        task=self.store.course_task(path)
        self.assertNotIn(held,[d['id'] for d in task['reservation_candidates']])
        result={'summary':'Primo parziale','included':['PRAM'],'excluded':['Secondo parziale'],'clarification':None,'recommended_reservations':[{'document':held,'reason':'Contiene PRAM'}]}
        with self.assertRaises(ValueError):self.store.course_commit(path,task,result)
        result['recommended_reservations']=[]
        self.store.course_commit(path,task,result)

    def test_exposed_or_non_exam_sources_cannot_be_recommended(self):
        inventory=self.store.course_inventory(self.course)['documents']
        exposed=next(d['id'] for d in inventory if d['exam'])
        with self.store.db:self.store.db.execute('INSERT INTO course_exposure VALUES(?,?,?)',(self.course,exposed,'2026-10-17'))
        path=self.store.course_create(self.course,engine=1,request='Primo parziale: PRAM')['id'];task=self.store.course_task(path)
        for did in [exposed,next(d['id'] for d in inventory if not d['exam'] and not d['solution'])]:
            with self.assertRaises(ValueError):self.store.course_commit(path,task,{'summary':'Primo parziale','included':['PRAM'],'excluded':[],'clarification':None,'recommended_reservations':[{'document':did,'reason':'Una motivazione'}]})

    def test_scope_requires_confirmation_and_keeps_general_request(self):
        self.start();p=self.store.course_path_view(self.path)
        self.assertEqual(p['objective']['request'],'Primo parziale: PRAM e prefix sum')
        self.assertTrue(p['objective']['confirmed']);self.assertTrue(self.store.course_task(self.path)['chunks'])
        other=self.store.course_create(self.course,engine=1,request='Esame completo di un altro programma',reserved=[])['id']
        self.assertEqual(self.store.course_task(other)['kind'],'scope')
        self.assertFalse(self.store.db.execute('SELECT 1 FROM course_units WHERE path=?',(other,)).fetchone())

    def test_heldout_questions_and_solutions_never_enter_training_tools(self):
        self.start()
        sources=self.store.db.execute('SELECT id FROM passages WHERE document=?',(self.held,)).fetchall()
        for r in sources:
            with self.assertRaises(ValueError):self.store.source(r[0])
        self.assertFalse(self.store.search(self.course,'Reserved unique'))
        task=self.store.course_task(self.path)
        self.assertNotIn('Reserved unique',json.dumps(task))
        self.assertFalse(self.store.grep_materials(self.sid,'Reserved unique'))
        self.assertFalse(self.store.db.execute('SELECT 1 FROM course_units WHERE path=? AND document=?',(self.path,self.held)).fetchone())
        with self.assertRaises(ValueError):self.store.read_material(self.sid,self.held)
        self.store.import_course(self.course)
        self.assertTrue(self.store.db.execute('SELECT reserved FROM passages WHERE document=?',(self.held,)).fetchone()[0])

    def test_reading_exposes_exact_allowed_citations_and_rejects_other_documents(self):
        self.start();task=self.store.course_task(self.path)
        self.assertEqual(set(task['allowed_sources']),{c['source'] for c in task['chunks']})
        other=self.store.db.execute('SELECT p.id FROM passages p JOIN documents d ON d.id=p.document WHERE p.course=? AND p.document!=? AND p.reserved=0 AND p.solution=0 LIMIT 1',(self.course,task['document'])).fetchone()[0]
        result={'summary':'Scheda con riferimento non letto','sources':[other]}
        with self.assertRaisesRegex(ValueError,'La scheda deve citare'):self.store.course_commit(self.path,task,result)
        self.assertEqual(self.store.course_task(self.path)['chunks'],task['chunks'])
        result['sources']=[task['chunks'][0]['source']]
        self.store.course_commit(self.path,task,result)
        self.assertNotEqual(self.store.course_task(self.path).get('chunks'),task['chunks'])

    def test_oversized_or_empty_cards_are_rejected_without_losing_checkpoint(self):
        self.start();task=self.store.course_task(self.path)
        self.assertEqual(task['card_limits']['max_characters'],16000)
        result={'summary':'x'*17000,'sources':[task['chunks'][0]['source']]}
        with self.assertRaisesRegex(ValueError,'Scheda fonte troppo lunga: .*limite 16000'):self.store.course_commit(self.path,task,result)
        self.assertEqual(self.store.course_task(self.path)['chunks'],task['chunks'])
        result['summary']='  '
        with self.assertRaisesRegex(ValueError,'Scheda fonte senza sintesi:'):self.store.course_commit(self.path,task,result)
        result['summary']='Sintesi compatta: PRAM e ipotesi di accesso alla memoria.'
        self.store.course_commit(self.path,task,result)
        self.assertNotEqual(self.store.course_task(self.path).get('chunks'),task['chunks'])

    def test_reading_checkpoints_resume_without_reanalysis(self):
        self.start();task=self.store.course_task(self.path)
        self.store.course_commit(self.path,task,{'summary':'Una scheda','sources':[c['source'] for c in task['chunks']]})
        finished=self.store.db.execute('SELECT count(*) FROM course_units WHERE path=? AND card IS NOT NULL',(self.path,)).fetchone()[0]
        other=Study(self.root)
        self.assertEqual(other.db.execute('SELECT count(*) FROM course_units WHERE path=? AND card IS NOT NULL',(self.path,)).fetchone()[0],finished)
        self.assertNotEqual(other.course_task(self.path).get('chunks'),task['chunks']);other.db.close()

    def test_plan_checks_coverage_sources_and_prerequisite_order(self):
        self.start();data=self.blueprint()
        bad=copy.deepcopy(data);bad['chapters'][0]['prerequisites']=['missing']
        with self.assertRaises(ValueError):self.store._validate_plan(self.path,bad)
        bad=copy.deepcopy(data);bad['chapters'][0]['coverage']=[]
        with self.assertRaises(ValueError):self.store._check_coverage(self.path,bad)
        bad=copy.deepcopy(data);bad['chapters'][0]['sources']=[self.held+':0']
        with self.assertRaises(ValueError):self.store._validate_plan(self.path,bad)

    def test_chapter_solutions_are_private_and_drafts_resume(self):
        self.prepare();view=self.store.view(self.sid);a=view['activities'][0]
        self.assertNotIn('answer',a['spec']);self.assertNotIn('solution',a['spec'])
        public=self.store.course_path_view(self.path)
        self.assertNotIn('solution',json.dumps(public['current']));self.assertNotIn('Un livello',json.dumps(public))
        self.store.event(self.sid,a['id'],1,'draft','change',{'answer':'La bozza'})
        self.store.course_position(self.sid,'practice')
        other=Study(self.root);resumed=other.course_open(self.path)
        self.assertEqual(resumed['activities'][0]['state']['answer'],'La bozza')
        self.assertEqual(other.course_path_view(self.path)['position']['block'],'practice');other.db.close()

    def test_exercises_require_solution_and_html_cannot_write_mastery(self):
        self.start();self.read_all();content=self.content();del content['blocks'][1]['spec']['solution']
        with self.assertRaises(ValueError):self.store._save_chapter(self.path,'pram',content)
        self.assertEqual(self.store.progress(self.course)[0]['status'],'da affrontare')
        with self.assertRaises(ValueError):self.store.course_note(self.sid,'fact','Ha imparato tutto')

    def test_journal_records_facts_once_and_keeps_interpretations_correctable(self):
        self.prepare();a=self.store.view(self.sid)['activities'][0]
        result=self.store.event(self.sid,a['id'],1,'answer','submit',{'answer':0})
        self.store.event(self.sid,a['id'],1,'answer','submit',{'answer':0})
        facts=self.store.course_journal(self.course,kind='fact');self.assertEqual(len(facts),1)
        with self.assertRaises(ValueError):self.store.course_note(self.sid,'hypothesis','Una difficoltà',[])
        note=self.store.course_note(self.sid,'hypothesis','Forse confonde lavoro e tempo',[result['attempt']['id']])
        self.store.course_correct_note(self.course,note['id'],'Era un errore di digitazione')
        self.assertTrue(any(n['correction'] for n in self.store.course_journal(self.course)))
        self.store.course_note(self.sid,'preference','Prima un esempio numerico')
        self.assertTrue(self.store.course_context(self.sid)['preferences'])

    def test_revisions_are_undoable_without_rewriting_completed_work(self):
        self.prepare();original=self.store._plan(self.path);mid=self.store.message(self.sid,'user','Vorrei un recupero con numeri concreti')
        data=copy.deepcopy(original['data']);data['chapters'].append({'id':'recovery','title':'Recupero','objective':'Distinguere lavoro e tempo','prerequisites':['pram'],'sources':[self.source],'priority':'alta','priority_reason':'Richiesta dello studente','assessment':'Esempio e variante','coverage':[]})
        revised=self.store.course_revise(self.sid,data,'Inserisco recupero mirato',[mid])
        self.assertEqual(len(revised['chapters']),2)
        self.store.course_undo(self.path,original['version'])
        self.assertEqual(len(self.store._plan(self.path)['data']['chapters']),1)
        self.assertEqual(self.store._chapter(self.path,'pram')['version'],1)
        bad=copy.deepcopy(data);bad['chapters'][0]['title']='Cambio retroattivo'
        with self.assertRaises(ValueError):self.store.course_revise(self.sid,bad,'Cambio',[mid])

    def test_new_explanation_versions_do_not_erase_attempts_or_pin(self):
        self.prepare();a=self.store.view(self.sid)['activities'][0]
        self.store.event(self.sid,a['id'],1,'attempt','submit',{'answer':1})
        self.store.course_append(self.sid,'pram','Un esempio diverso',[self.source],'Preferenza dello studente')
        self.assertEqual(self.store.course_path_view(self.path)['current']['version'],1)
        self.store.course_select(self.sid,'pram',version=2)
        self.assertEqual(len(self.store.view(self.sid)['attempts']),1)
        self.assertEqual(self.store.course_path_view(self.path)['current']['version'],2)

    def test_source_change_invalidates_only_dependent_chapter(self):
        self.prepare();s=self.store.source(self.source)
        with self.store.db:self.store.db.execute('UPDATE documents SET fingerprint=? WHERE id=?',('changed',s['document']))
        self.assertTrue(self.store.course_path_view(self.path)['current']['stale'])
        self.assertEqual(self.store.course_task(self.path)['kind'],'reading')
        with self.assertRaises(ValueError):self.store.course_select(self.sid,'pram')

    def test_simulation_has_no_aids_or_training_context_and_unlock_marks_exposed(self):
        self.start();v=self.store.course_simulation(self.path,self.held);sid=v['session']['id'];a=v['activities'][0]
        self.assertEqual(v['session']['mode'],'exam');self.assertIsNone(self.store.course_context(sid))
        self.assertNotIn('Reserved unique answer',a['spec']['prompt'])
        with self.assertRaises(ValueError):self.store.event(sid,a['id'],1,'hint','hint',{})
        with self.assertRaises(ValueError):self.store.course_evidence(sid)
        self.store.course_unlock(self.path,self.held)
        self.assertTrue(next(d for d in self.store.course_inventory(self.course)['documents'] if d['id']==self.held)['exposed'])
        self.assertFalse(self.store.db.execute('SELECT reserved FROM passages WHERE document=?',(self.held,)).fetchone()[0])

    def test_multiple_sessions_share_plan_and_diary_but_preserve_separate_drafts(self):
        self.prepare();self.store.course_position(self.sid,'practice');a=self.store.view(self.sid)['activities'][0]
        self.store.event(self.sid,a['id'],1,'old-draft','change',{'answer':'Vecchia bozza'})
        self.store.course_note(self.sid,'preference','Usa esempi numerici')
        fresh=self.store.course_open(self.path,fresh=True)
        self.assertNotEqual(fresh['session']['id'],self.sid)
        self.assertEqual(fresh['curriculum']['block'],'practice')
        self.assertFalse(fresh['activities'][0]['state'])
        self.assertTrue(self.store.course_context(fresh['session']['id'])['preferences'])
        restored=self.store.course_open(self.path,sid=self.sid)
        self.assertEqual(restored['activities'][0]['state']['answer'],'Vecchia bozza')

    def test_preferences_invalidate_future_content_without_rewriting_current_chapter(self):
        self.prepare();old=self.store._plan(self.path);mid=self.store.message(self.sid,'user','Aggiungi un recupero')
        data=json.loads(json.dumps(old['data']));data['chapters'].append({'id':'future','title':'Futuro','objective':'Esercitarsi','prerequisites':['pram'],'sources':[self.source],'priority':'alta','priority_reason':'Richiesta','assessment':'Variante','coverage':[]})
        self.store.course_revise(self.sid,data,'Recupero richiesto',[mid]);self.store._save_chapter(self.path,'future',self.content())
        self.assertFalse(self.store._chapter_stale(self.store._chapter(self.path,'future')))
        self.store.course_note(self.sid,'preference','Prima esempi concreti')
        self.assertFalse(self.store._chapter_stale(self.store._chapter(self.path,'pram')))
        self.assertTrue(self.store._chapter_stale(self.store._chapter(self.path,'future')))
        self.assertEqual(self.store.course_task(self.path)['chapter']['id'],'future')

    def test_recall_is_new_and_has_no_aids_and_returns_to_saved_point(self):
        self.prepare();self.store.course_position(self.sid,'practice')
        spec=dict(self.content()['blocks'][1]['spec'],prompt='Quattro valori: quanti livelli?',answer=2)
        recalled=self.store.course_create_recall(self.sid,'pram',spec);a=recalled['activities'][-1]
        self.assertTrue(self.store.course_context(self.sid)['recall'])
        with self.assertRaises(ValueError):self.store.event(self.sid,a['id'],1,'recall-hint','hint',{})
        self.store.event(self.sid,a['id'],1,'recall-answer','submit',{'answer':2})
        self.assertFalse(self.store.course_context(self.sid)['recall'])
        self.assertEqual(self.store.course_path_view(self.path)['position']['block'],'practice')
        with self.assertRaises(ValueError):self.store.course_create_recall(self.sid,'pram',spec)

    def test_agent_preferences_need_user_evidence_and_notes_link_to_actual_attempts(self):
        self.prepare()
        with self.assertRaises(ValueError):self.store.course_note(self.sid,'preference','Inventata',agent=True)
        mid=self.store.message(self.sid,'user','Preferisco esempi concreti')
        note=self.store.course_note(self.sid,'preference','Esempi concreti',[mid],agent=True)
        self.assertEqual(self.store.course_note_evidence(self.course,note['id'])[0]['text'],'Preferisco esempi concreti')
        with self.assertRaises(ValueError):self.store.course_note(self.sid,'preference','Globale',[mid],agent=True,global_preference=True)

    def test_scope_cannot_read_exam_text_before_reservations_are_confirmed(self):
        self.start();doc=self.store.source(self.source)['document']
        with self.assertRaises(ValueError):self.store.course_scope_material(self.sid,doc)
        with self.assertRaises(ValueError):self.store.course_scope_material(self.sid,self.held)

    def test_checkpoint_commit_is_idempotent_and_coverage_records_ranges(self):
        self.start();task=self.store.course_task(self.path);result={'summary':'Scheda','sources':[c['source'] for c in task['chunks']]}
        self.store.course_commit(self.path,task,result);first=self.store.course_coverage(self.path,task['document'])
        self.store.course_commit(self.path,task,result)
        self.assertEqual(first,self.store.course_coverage(self.path,task['document']))
        self.assertTrue(all(r['done'] and r['end']>r['start'] for r in first))
        with self.assertRaises(ValueError):self.store.course_commit(self.path,task,dict(result,summary='Modifica retroattiva'))

    def test_out_of_scope_questions_do_not_distort_exam_profile(self):
        self.start();task=self.store.course_task(self.path)
        refs=[c['source'] for c in task['chunks']]
        q={'text':'Describe a second-part pattern','format':'open','in_scope':False,'skills':['Patterns'],'sources':refs,'points':1}
        self.store.course_commit(self.path,task,{'summary':'Fuori perimetro','sources':refs,'questions':[q]})
        profile=self.store.course_exam_profile(self.path)
        self.assertEqual(profile['total'],0);self.assertEqual(profile['excluded_total'],0)  # A classroom question is not an exam occurrence.

    def test_compatible_chapter_update_preserves_draft_and_old_activity_version(self):
        self.prepare();a=self.store.view(self.sid)['activities'][0]
        self.store.event(self.sid,a['id'],1,'compatible-draft','change',{'answer':'La bozza compatibile'})
        self.store.course_append(self.sid,'pram','Un approfondimento',[self.source],'Richiesta')
        self.store.course_select(self.sid,'pram',version=2)
        blocks=self.store.course_path_view(self.path)['current']['content']['blocks']
        exercise=next(b for b in blocks if b['kind']=='activity')
        self.assertEqual(exercise['activity'],a['id']);self.assertEqual(exercise['activity_version'],2)
        self.assertEqual(self.store.activity(self.sid,a['id'],2)['state']['answer'],'La bozza compatibile')
        self.assertEqual(self.store.activity(self.sid,a['id'],1)['state']['answer'],'La bozza compatibile')

    def test_exam_used_in_preparation_is_not_proposed_as_new_again(self):
        self.start();self.read_all()
        inventory=self.store.course_inventory(self.course)
        training=next(d for d in inventory['documents'] if d['title']=='PC-1st-part-25-06-19.pdf')
        self.assertTrue(training['exposed']);self.assertNotIn(training['id'],inventory['proposed'])

    def test_progress_separates_aided_autonomous_and_delayed_provisional_evidence(self):
        from datetime import datetime,timezone,timedelta
        self.prepare();a=self.store.view(self.sid)['activities'][0]
        self.store.event(self.sid,a['id'],1,'aid','hint',{})
        self.store.event(self.sid,a['id'],1,'aided-success','submit',{'answer':1})
        self.assertEqual(self.store.course_progress(self.path)['pram']['status'],'riuscito con aiuti')
        spec=dict(self.content()['blocks'][1]['spec'],prompt='Quattro valori: quanti livelli nuovi?',answer=2)
        v=self.store.course_create_recall(self.sid,'pram',spec);a=v['activities'][-1]
        first=self.store.event(self.sid,a['id'],1,'autonomous-success','submit',{'answer':2})
        self.assertEqual(self.store.course_progress(self.path)['pram']['status'],'riuscito autonomamente')
        with self.store.db:self.store.db.execute('UPDATE attempts SET created=? WHERE id=?',((datetime.now(timezone.utc)-timedelta(days=2)).isoformat(),first['attempt']['id']))
        spec=dict(spec,prompt='Sedici valori: quanti livelli in una nuova prova?',answer=4)
        v=self.store.course_create_recall(self.sid,'pram',spec);a=v['activities'][-1]
        self.store.event(self.sid,a['id'],1,'delayed-success','submit',{'answer':4})
        progress=self.store.course_progress(self.path)['pram']
        self.assertEqual(progress['status'],'riconfermato a distanza');self.assertTrue(progress['provisional'])

    def test_administrative_results_are_not_sent_to_preparation(self):
        folder=self.root/'corsi'/self.course/'materiali'/'results';folder.mkdir()
        (folder/'elenco.txt').write_text('Test Student, identifier 0000, exam result 20')
        self.store.import_course(self.course);self.start()
        inventory=self.store.course_inventory(self.course)
        admin=next(d for d in inventory['documents'] if d['title']=='elenco.txt')
        self.assertTrue(admin['administrative'])
        self.assertFalse(self.store.db.execute('SELECT 1 FROM course_units WHERE path=? AND document=?',(self.path,admin['id'])).fetchone())
