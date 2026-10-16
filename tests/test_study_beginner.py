import json
import unittest
from pathlib import Path
from tests import test_study as fixtures
pymupdf=fixtures.pymupdf
from polimi_lectures.study import Study

@unittest.skipIf(pymupdf is None,'Requires native slides runtime')
class BeginnerTest(unittest.TestCase):
    setUp=fixtures.StudyTest.setUp
    tearDown=fixtures.StudyTest.tearDown

    def start(self):
        self.view=self.store.open_session(self.course,fresh=True,approach='beginner')
        self.sid=self.view['session']['id']
        self.lesson=self.view['learning']['lesson']['id']
        self.source=self.store.lesson_bundle(self.sid)['passages'][0]['id']
        return self.view

    def plan(self):
        return self.store.set_lesson_plan(self.sid,self.lesson,[{'title':'PRAM','objective':'Spiegare il modello senza assumere sigle note.','prerequisites':['Algoritmo','Processore'],'sources':[self.source]}])

    def test_begins_without_unexplained_quiz_and_keeps_source_order(self):
        folder=self.root/'corsi'/self.course/'000-earlier-lesson'/'trascrizione';folder.mkdir(parents=True)
        (folder/'trascrizione.json').write_text(json.dumps({'segments':[{'start':0,'end':10,'text':'Start with sequential algorithms before parallel execution.'}]}))
        self.store.import_course(self.course)
        view=self.start()
        self.assertEqual(view['activities'],[])
        self.assertIn('000-earlier-lesson',view['learning']['lesson']['path'])
        self.assertEqual(view['learning']['phase'],'orientation')
        self.assertEqual(self.store.context(self.sid)['learning']['lesson']['id'],self.lesson)
        self.assertFalse(any('EREW' in m['text'] for m in view['messages']))

    def test_plan_requires_anchor_and_generated_activities_keep_provenance(self):
        self.start()
        pdf=self.store.search(self.course,'exclusive')[0]['id']
        with self.assertRaises(ValueError):self.store.set_lesson_plan(self.sid,self.lesson,[{'title':'Fake','objective':'Missing lecture source','sources':[pdf]}])
        self.plan()
        with self.assertRaises(ValueError):self.store.create_activity(self.sid,{'kind':'explain','title':'No citation','prompt':'Unsupported','sources':[]})
        a=self.store.create_activity(self.sid,{'kind':'explain','title':'Dalle basi','prompt':'Un algoritmo è una sequenza di passi.','sources':[self.source],'concept':'pram','grading_origin':'curated'})
        spec=self.store.activity(self.sid,a['id'],1)['spec']
        self.assertEqual(spec['beginner']['phase'],'foundations')
        self.assertEqual(spec['grading_origin'],'generated')
        self.assertEqual(spec['concept'],self.lesson+':0')

    def test_phases_resume_without_awarding_mastery_and_schedule_recall(self):
        self.start();self.plan()
        for expected in ['explain','worked','guided','independent']:
            v=self.store.advance_beginner(self.sid)
            self.assertEqual(v['learning']['phase'],expected)
        a=self.store.create_activity(self.sid,{'kind':'numeric','title':'Una variante','prompt':'Quanto?','answer':4,'sources':[self.source]})
        result=self.store.event(self.sid,a['id'],1,'beginner-submit','submit',{'answer':4})
        self.assertEqual(result['attempt']['grade']['status'],'provisional')
        self.store.advance_beginner(self.sid)
        other=Study(self.root)
        resumed=other.open_session(self.course)
        self.assertEqual(resumed['session']['id'],self.sid)
        self.assertEqual(resumed['learning']['phase'],'recap')
        self.assertEqual(len(resumed['learning']['recalls']),1)
        self.assertTrue(resumed['learning']['navigation_is_not_mastery'])
        other.db.close()

    def test_recall_returns_to_original_lesson_cursor(self):
        self.start();self.plan()
        self.store.advance_beginner(self.sid)
        self.assertEqual(self.store.beginner_context(self.sid)['phase'],'explain')
        self.store.beginner_recall(self.sid,self.lesson,0)
        self.assertEqual(self.store.beginner_context(self.sid)['phase'],'recall')
        self.store.advance_beginner(self.sid)
        self.assertEqual(self.store.beginner_context(self.sid)['phase'],'explain')

    def test_topic_switch_keeps_previous_phase(self):
        self.start()
        units=[{'title':title,'objective':'Spiegare '+title,'sources':[self.source],'prerequisites':[]} for title in ['Algoritmi','Processori']]
        self.store.set_lesson_plan(self.sid,self.lesson,units)
        self.store.advance_beginner(self.sid)
        self.store.select_beginner_unit(self.sid,1)
        self.assertEqual(self.store.beginner_context(self.sid)['phase'],'foundations')
        self.store.select_beginner_unit(self.sid,0)
        self.assertEqual(self.store.beginner_context(self.sid)['phase'],'explain')

    def test_ocr_only_lesson_is_visible_but_not_a_verified_transcript(self):
        alignment=self.root/'corsi'/self.course/'2026-10-01_missing_transcript'/'allineamento';alignment.mkdir(parents=True)
        (alignment/'allineamento.json').write_text(json.dumps({'intervals':[{'start':10,'end':20,'ocr':'Parallel sum','status':'candidate','confidence':'medium','material':{'file':'lecture.pdf','page':1}}]}))
        self.store.import_course(self.course);self.start()
        lessons=self.store.beginner_context(self.sid)['lessons']
        ocr=next(l for l in lessons if l['kind']=='alignment')
        self.assertIn('non disponibile',ocr['quality'])
        self.store.select_lesson(self.sid,ocr['id'])
        bundle=self.store.lesson_bundle(self.sid)
        self.assertEqual(bundle['passages'][0]['metadata']['alignment']['status'],'candidate')

    def test_linked_pdf_preserves_candidate_status_and_pagination(self):
        alignment=self.root/'corsi'/self.course/'lesson'/'allineamento';alignment.mkdir()
        (alignment/'allineamento.json').write_text(json.dumps({'intervals':[{'start':10,'end':20,'ocr':'PRAM','status':'candidate','confidence':'medium','material':{'file':'lecture.pdf','page':1}}]}))
        self.store.import_course(self.course);self.start()
        bundle=self.store.lesson_bundle(self.sid,limit=1)
        self.assertEqual(bundle['linked_materials'][0]['status'],'candidate')
        self.assertEqual(bundle['linked_materials'][0]['page'],1)
        self.assertEqual(bundle['total_passages'],1)
        self.assertEqual(self.store.lesson_bundle(self.sid,offset=1)['passages'],[])

    def test_material_only_path_uses_natural_order_and_does_not_include_exams(self):
        other='other-course-2026'
        materials=self.root/'corsi'/other/'materiali';materials.mkdir(parents=True)
        for n in [10,2]:
            doc=pymupdf.open();page=doc.new_page();page.insert_text((20,30),'Cells and basic biology.');doc.save(materials/('lecture%d.pdf'%n));doc.close()
        self.store.import_course(other)
        view=self.store.open_session(other,fresh=True,approach='beginner')
        self.assertEqual(view['learning']['lesson']['label'],'lecture2.pdf')
        self.assertIn('non cronologia verificata',view['learning']['lesson']['quality'])
        with self.assertRaises(ValueError):self.store.lesson_bundle(view['session']['id'],lesson=self.store.course_lessons(self.course)[0]['id'])
        exam=self.store.open_session(self.course,mode='exam',fresh=True)['session']['id']
        with self.assertRaises(ValueError):self.store.lesson_bundle(exam)

if __name__=='__main__':unittest.main()
