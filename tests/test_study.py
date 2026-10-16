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


if __name__=='__main__':unittest.main()
