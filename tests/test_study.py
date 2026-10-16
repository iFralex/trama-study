import json
import tempfile
import unittest
from pathlib import Path

try:
    import pymupdf
except ImportError:
    pymupdf=None

from polimi_lectures.study import Study


@unittest.skipIf(pymupdf is None, 'Requires the native slides runtime')
class StudyTest(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name)
        self.course='a-course-2025-26'
        materials=self.root/'corsi'/self.course/'materiali'
        materials.mkdir(parents=True)
        for name,text in [
            ('lecture.pdf','PRAM: EREW exclusive read exclusive write. CREW concurrent read exclusive write. CRCW concurrent read concurrent write. Reduction sum and prefix scan.'),
            ('PC-1st-part-25-06-19.pdf','Parallel Computing I part - February 12th, 2025\nExercise 1\nA. What is the difference between EREW, CREW, and CRCW models? Provide an example for each of them. (1)\n____________________'),
            ('PC-1st-part-25-06-19.sol.pdf','Official solution: EREW, CREW, CRCW.'),
            ('PC-1st-part-25-07-21.pdf','Reserved unique question. Explain PRAM.'),
            ('PC-1st-part-25-07-21.sol.pdf','Reserved unique answer.'),
        ]:
            doc=pymupdf.open();page=doc.new_page();page.insert_textbox(pymupdf.Rect(30,30,550,780),text);doc.save(materials/name);doc.close()
        (materials/'test.ipynb').write_text(json.dumps({'cells':[{'cell_type':'code','source':['x=1\n','<!-- hidden solution -->']}]}))
        lesson=self.root/'corsi'/self.course/'lesson'/'trascrizione'
        lesson.mkdir(parents=True)
        (lesson/'trascrizione.json').write_text(json.dumps({'segments':[{'start':10,'end':20,'text':'This is the PRAM reduction explanation.'}]}))
        self.store=Study(self.root)
        self.report=self.store.import_course(self.course)
        self.view=self.store.open_session(self.course)
        self.sid=self.view['session']['id']

    def tearDown(self):
        self.store.db.close();self.tmp.cleanup()

    def current(self):
        v=self.store.view(self.sid)
        return next(a for a in reversed(v['activities']) if a['id']==v['session']['current'])

    def event(self,kind,payload,identity='event'):
        a=self.current()
        return self.store.event(self.sid,a['id'],a['version'],identity,kind,payload)

    def test_incremental_import_quality_and_conflicting_dates(self):
        self.assertTrue(self.report['issues'])
        self.assertEqual(self.store.import_course(self.course)['changed'],0)
        found=self.store.search(self.course,'riduzione')
        self.assertTrue(any('Reduction' in s['text'] for s in found))
        self.assertTrue(any(s['quality']=='trascrizione parziale' for s in self.store.search(self.course,'PRAM')))
        self.assertFalse(any('hidden solution' in s['text'] for s in self.store.search(self.course,'hidden')))

    def test_drafts_survive_reopen_and_events_are_idempotent(self):
        self.event('change',{'answer':'CREW'})
        other=Study(self.root)
        reopened=other.open_session(self.course)
        self.assertEqual(reopened['session']['id'],self.sid)
        self.assertEqual(reopened['activities'][-1]['state']['answer'],'CREW')
        duplicate=self.event('change',{'answer':'CREW'})
        self.assertTrue(duplicate['duplicate'])
        with self.assertRaises(ValueError):self.event('change',{'answer':'CRCW'})
        other.db.close()

    def test_wrong_hint_correct_progress_and_no_answer_in_browser(self):
        self.assertNotIn('answer',self.current()['spec'])
        first=self.event('submit',{'answer':'EREW'},'wrong')
        self.assertFalse(first['attempt']['grade']['correct'])
        self.event('hint',{},'hint')
        second=self.event('submit',{'answer':'CREW'},'right')
        self.assertTrue(second['attempt']['grade']['correct'])
        self.assertEqual(second['attempt']['aids'],1)
        self.assertEqual(self.store.progress(self.course)[0]['status'],'riuscito con aiuti')
        duplicate=self.event('submit',{'answer':'CREW'},'right')
        self.assertTrue(duplicate['duplicate'])
        self.assertEqual(len(self.store.view(self.sid)['attempts']),2)

    def test_generated_activity_cannot_award_verified_mastery(self):
        a=self.store.create_activity(self.sid,{'kind':'numeric','title':'Generated','prompt':'One?','answer':1,'concept':'scan','sources':[],'grading_origin':'curated'})
        result=self.store.event(self.sid,a['id'],a['version'],'generated','submit',{'answer':1,'correct':True,'status':'verified'})
        self.assertEqual(result['attempt']['grade']['status'],'provisional')
        with self.assertRaises(ValueError):self.store.review(self.course,'scan',{'due':'2099-01-01'},result['attempt']['id'])

    def test_version_keeps_state_and_previous_attempt(self):
        a=self.current()
        self.event('change',{'answer':'CREW'},'draft')
        self.event('submit',{'answer':'CREW'},'answer')
        new=self.store.create_activity(self.sid,dict(a['spec'],title='Revised'),a['id'])
        self.assertEqual(new['version'],2)
        view=self.store.view(self.sid)
        self.assertEqual(view['activities'][-1]['state']['answer'],'CREW')
        self.assertEqual(view['attempts'][0]['version'],1)
        selected=self.store.select_activity(self.sid,a['id'],1)
        self.assertEqual(selected['session']['current_version'],1)
        self.assertEqual(self.store.context(self.sid)['activity']['version'],1)

    def test_reserved_exam_and_solutions_are_isolated(self):
        self.assertFalse(self.store.search(self.course,'Reserved'))
        exam=self.store.open_session(self.course,mode='exam',fresh=True)
        sid=exam['session']['id'];a=exam['activities'][-1]
        self.assertIn('Reserved unique question',a['spec']['prompt'])
        with self.assertRaises(ValueError):self.store.event(sid,a['id'],1,'h','hint',{})
        with self.assertRaises(ValueError):self.store.create_activity(sid,{'kind':'explain','title':'cheat'})
        self.assertFalse(any(r['solution'] for r in self.store.search(self.course,'official',mode='exam')))
        with self.assertRaises(ValueError):self.store.assessment(sid,'not-submitted')
        attempt=self.store.event(sid,a['id'],1,'exam-delivery','submit',{'answer':'Independent answer.'})['attempt']
        assessment=self.store.assessment(sid,attempt['id'])
        self.assertTrue(any(s['solution'] and 'Reserved unique answer' in s['text'] for s in assessment['sources']))

    def test_authentic_question_variant_and_delayed_recall(self):
        for _ in range(5):self.store.next(self.sid)
        question=self.current()['spec']
        self.assertTrue(question['authentic'])
        self.assertIn('What is the difference',question['prompt'])
        self.store.next(self.sid)
        result=self.event('submit',{'answer':'8'},'variant')
        self.assertTrue(result['attempt']['grade']['correct'])
        recall=self.store.recall(self.sid,'reduction')
        a=recall['activities'][-1]
        self.assertIn('64 valori',a['spec']['prompt'])
        result=self.store.event(self.sid,a['id'],1,'recall','submit',{'answer':17})
        self.assertTrue(result['attempt']['grade']['correct'])

    def test_correction_preserves_grade_but_excludes_mastery(self):
        result=self.event('submit',{'answer':'CREW'},'correct')
        self.store.correct(self.sid,result['attempt']['id'],'I accidentally clicked the answer.')
        self.assertTrue(self.store.view(self.sid)['attempts'][0]['grade']['correct'])
        self.assertEqual(self.store.progress(self.course)[0]['status'],'affrontato')

    def test_other_courses_and_unavailable_disk(self):
        other='biology-2026'
        materials=self.root/'corsi'/other/'materiali';materials.mkdir(parents=True)
        doc=pymupdf.open();page=doc.new_page();page.insert_text((30,40),'Biology: cells and enzymes.');doc.save(materials/'intro.pdf');doc.close()
        self.store.import_course(other)
        view=self.store.open_session(other)
        self.assertEqual(view['activities'][-1]['spec']['title'],'Scegli il tuo obiettivo')
        self.assertEqual(view['progress'],[])
        self.assertFalse(self.store.search(other,'PRAM'))
        with self.assertRaises(ValueError):self.store.course_path('../escape')
        with self.assertRaises(ValueError):Study(self.root/'missing')

    def test_delayed_success_requires_new_problem_and_a_day(self):
        first=self.event('submit',{'answer':'CREW'},'first')
        self.store.db.execute('UPDATE attempts SET created=? WHERE id=?',('2026-01-01T00:00:00+00:00',first['attempt']['id']))
        self.store.db.commit()
        recall=self.store.recall(self.sid,'pram');a=recall['activities'][-1]
        self.store.event(self.sid,a['id'],1,'delayed','submit',{'answer':'CRCW'})
        self.assertEqual(self.store.progress(self.course)[0]['status'],'riconfermato a distanza')

    def test_file_navigation_matches_citations_and_lines(self):
        docs=self.store.list_materials(self.sid,'lecture.pdf')
        self.assertEqual(len(docs),1)
        hits=self.store.grep_materials(self.sid,'exclusive',docs[0]['id'])
        self.assertTrue(hits)
        excerpt=self.store.read_material(self.sid,docs[0]['id'],hits[0]['line'],hits[0]['line'])
        self.assertEqual(excerpt['lines'][0]['source'],hits[0]['source'])
        self.assertEqual(excerpt['lines'][0]['text'],hits[0]['text'])
        self.assertFalse(self.store.grep_materials(self.sid,'Reserved unique'))
        with self.assertRaises(ValueError):self.store.read_material(self.sid,'../../secret')
        materials=self.root/'corsi'/self.course/'materiali'
        (materials/'kernel.cu').write_text('__global__ void sum() {\n  int i = threadIdx.x;\n}')
        (materials/'Links.html').write_text('<p>Course links</p><script>hidden_script</script>')
        self.store.import_course(self.course)
        self.assertTrue(self.store.grep_materials(self.sid,'threadIdx.x'))
        self.assertFalse(self.store.grep_materials(self.sid,'hidden_script'))

    def test_history_search_restore_and_exam_context_block(self):
        self.store.message(self.sid,'user','Riprendiamo la riduzione ad albero')
        self.event('change',{'answer':'saved history draft'},'historydraft')
        other=self.store.open_session(self.course,fresh=True)['session']['id']
        found=self.store.list_sessions(self.course,'riduzione',sid=other)
        self.assertEqual(found[0]['id'],self.sid)
        history=self.store.read_session(other,self.sid)
        self.assertIn('riduzione',history['messages'][-1]['text'])
        self.assertEqual(history['activities'][-1]['state']['answer'],'saved history draft')
        self.assertEqual(self.store.session(other)['id'],other)
        self.store.resume_session(self.sid)
        self.assertEqual(self.store.open_session(self.course)['session']['id'],self.sid)
        exam=self.store.open_session(self.course,mode='exam',fresh=True)['session']['id']
        with self.assertRaises(ValueError):self.store.read_session(exam,self.sid)
        with self.assertRaises(ValueError):self.store.list_sessions(sid=exam)
        with self.assertRaises(ValueError):self.store.list_materials(exam)
        with self.assertRaises(ValueError):self.store.grep_materials(exam,'answer')

    def test_semantic_index_incremental_stale_and_permissions(self):
        from polimi_lectures.study import key
        batch=self.store.embedding_batch(self.course,'test-model',32)
        vector=[1.0]+[0.0]*383
        self.store.save_embeddings('test-model',[{'id':p['id'],'fingerprint':p['fingerprint'],'vectors':[vector]} for p in batch['items']])
        self.assertEqual(self.store.embedding_batch(self.course,'test-model')['pending'],0)
        results=self.store.semantic_search(self.course,vector,'test-model')
        self.assertTrue(results)
        self.assertFalse(any(s['reserved'] for s in results))
        with self.assertRaises(ValueError):self.store.semantic_search(self.course,vector,'test-model',mode='exam')
        source=results[0]['id']
        with self.store.db:self.store.db.execute('UPDATE passages SET text=? WHERE id=?',('changed text',source))
        self.assertFalse(any(r['id']==source for r in self.store.semantic_search(self.course,vector,'test-model')))
        self.assertEqual(self.store.embedding_batch(self.course,'test-model')['pending'],1)
        other=Study(self.root)
        self.assertEqual(other.embedding_batch(self.course,'test-model')['pending'],1)
        other.db.close()
        with self.assertRaises(ValueError):self.store.save_embeddings('test-model',[{'id':source,'fingerprint':key('changed text'),'vectors':[[float('nan')]*384]}])


if __name__=='__main__':unittest.main()
