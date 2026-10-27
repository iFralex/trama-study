import copy
import json
import time
import unittest
from tests import test_study as fixtures
from tests import test_study_course as course_fixtures
from polimi_lectures.study_course import pack, stamp
from polimi_lectures.study_time import block_effort, visible_metrics, fingerprint

class EffortTest(unittest.TestCase):
    def test_visible_only_code_math_and_languages(self):
        block={'id':'q','kind':'activity','spec':{'kind':'open','prompt':'Explain the argument.','solution':'hidden '*10000,'rubric':'hidden '*10000,'answer':'hidden'}}
        short=block_effort(block);block['spec']['solution']='hidden '*20000
        self.assertEqual(short['base'],block_effort(block)['base'])
        metrics=visible_metrics('Words $a<b$ and $$T(n)=n^2$$\n```cpp\nfor (int i=0; i<n; i++) {\n  x += i;\n}\n```\n[Source](source:doc:0)')
        self.assertEqual(metrics['inline_formulas'],1);self.assertEqual(metrics['display_formulas'],1);self.assertEqual(metrics['code_lines'],3)
        self.assertGreater(visible_metrics('你好世界学习知识')['words'],1)
        self.assertEqual(visible_metrics('![A diagram](local-diagram.png)')['images'],1)
        self.assertLess(block_effort({'id':'q','kind':'text','text':'Hello'})['base'],short['base'])

@unittest.skipIf(fixtures.pymupdf is None,'Requires native slides runtime')
class StudyTimeTest(unittest.TestCase):
    setUp=fixtures.StudyTest.setUp
    tearDown=fixtures.StudyTest.tearDown
    start=course_fixtures.CourseTest.start
    blueprint=course_fixtures.CourseTest.blueprint
    read_all=course_fixtures.CourseTest.read_all
    content=course_fixtures.CourseTest.content
    prepare=course_fixtures.CourseTest.prepare

    def estimate(self):
        return self.store.course_study_time(self.path,self.sid)

    def mark(self,block='intro',status='studied',version=1):
        return self.store.study_time_mark(self.sid,'pram',version,block,status)

    def record(self,id='interval',started=None,ended=None,seconds=30,block='intro',version=1):
        ended=ended if ended is not None else time.time()*1000-1000
        started=started if started is not None else ended-30000
        return self.store.study_time_record(self.sid,'pram',version,block,id,started,ended,seconds)

    def test_future_chapters_and_visible_content_without_reading_sources(self):
        self.prepare();plan=self.store._plan(self.path)['data'];plan=copy.deepcopy(plan)
        plan['chapters'].append(dict(plan['chapters'][0],id='future',title='A different topic',exam_skills=['One','Two','Three','Four','Five'],prerequisites=['pram']))
        with self.store.db:self.store.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)',(self.path,self.store._plan(self.path)['version']+1,pack(plan),'Test',stamp()))
        # The estimator consumes stored structure, not originals/holdouts/model tools.
        self.store.source=lambda *a,**k: (_ for _ in ()).throw(AssertionError('No source access'))
        self.store.course_exam_profile=lambda p:{'formats':{'open':2}}
        result=self.estimate();self.assertEqual(len(result['chapters']),2);self.assertEqual(result['forecast_chapters'],1)
        self.assertEqual(result['chapters'][0]['basis'],'content');self.assertEqual(result['chapters'][1]['basis'],'plan')
        self.assertGreater(result['chapters'][1]['total']['high'],result['chapters'][1]['total']['low'])
        self.assertEqual(result['total']['high'],sum(c['total']['high'] for c in result['chapters']))

    def test_explicit_progress_does_not_follow_scroll_or_subtract_elapsed_time(self):
        self.prepare();initial=self.estimate();self.store.course_position(self.sid,'practice')
        self.record();self.assertEqual(initial['remaining'],self.estimate()['remaining'])
        studied=self.mark();self.assertLess(studied['remaining']['high'],initial['remaining']['high'])
        review=self.mark(status='review');self.assertGreater(review['current_blocks'][0]['remaining']['high'],studied['current_blocks'][0]['remaining']['high']);self.assertGreaterEqual(review['remaining']['high'],studied['remaining']['high'])
        reset=self.mark(status='todo');self.assertEqual(reset['remaining'],initial['remaining'])
        self.assertEqual(self.store.course_progress(self.path)['pram']['status'],'affrontato')

    def test_submission_updates_remaining_without_claiming_mastery(self):
        self.prepare();initial=self.estimate();self.store.course_position(self.sid,'practice')
        activity=self.store.db.execute('SELECT activity,activity_version FROM course_chapter_activities WHERE session=?',(self.sid,)).fetchone()
        self.store.event(self.sid,activity[0],activity[1],'attempt-time-test','submit',{'answer':1})
        result=self.estimate();practice=next(b for b in result['current_blocks'] if b['id']=='practice')
        self.assertTrue(practice['submitted']);self.assertLess(result['remaining']['high'],initial['remaining']['high'])
        self.assertGreater(practice['remaining']['high'],0)

    def test_retries_and_overlapping_tabs_count_once(self):
        self.prepare();end=time.time()*1000-1000;start=end-30000
        self.assertAlmostEqual(self.record(started=start,ended=end)['seconds'],30)
        self.assertTrue(self.record(started=start,ended=end)['duplicate'])
        self.assertEqual(self.record(id='overlap',started=start,ended=end)['seconds'],0)
        self.assertAlmostEqual(self.record(id='partial',started=start+15000,ended=end+15000)['seconds'],15)
        self.assertEqual(self.estimate()['recorded_minutes'],.8)
        with self.assertRaises(ValueError):self.record(seconds=float('nan'))
        with self.assertRaises(ValueError):self.record(id='too-long',seconds=120)
        with self.assertRaises(ValueError):self.record(id='interval',started=start-1,ended=end)

    def test_versioned_marks_and_pinned_content_survive_reopen(self):
        self.prepare();self.mark();old=self.estimate();new=copy.deepcopy(self.content());new['blocks'][0]['text']='Changed text with new material.'
        self.store._save_chapter(self.path,'pram',new)
        pinned=self.estimate();self.assertEqual(pinned['chapters'][0]['version'],1);self.assertEqual(pinned['current_blocks'][0]['status'],'studied')
        self.store.course_select(self.sid,'pram',version=2);changed=self.estimate();self.assertEqual(changed['current_blocks'][0]['status'],'todo')
        visible=self.store.course_study_time(self.path,self.sid,chapter='pram',version=1);self.assertEqual(visible['current_blocks'][0]['status'],'studied')
        self.store._study_time_cache.clear();self.assertEqual(changed,self.estimate())

    def test_settings_schedule_recalls_and_no_plan(self):
        self.start();empty=self.estimate();self.assertFalse(empty['available'])
        self.read_all();task=self.store.course_task(self.path);self.store.course_commit(self.path,task,self.content());self.store.course_select(self.sid,'pram')
        result=self.store.study_time_settings(self.path,45,False,self.sid)
        self.assertEqual(result['daily_minutes'],45);self.assertFalse(result['tracking']);self.assertTrue(self.record().get('disabled'))
        self.assertEqual(result['study_days']['high'],__import__('math').ceil(result['remaining']['high']/45))
        with self.store.db:self.store.db.execute('INSERT INTO course_recalls VALUES(?,?,?,?)',(self.path,'pram',pack({'due':'2030-01-01'}),None))
        recalled=self.estimate();self.assertEqual(recalled['scheduled_recalls']['count'],1)
        self.assertEqual(recalled['remaining'],result['remaining'])
        with self.assertRaises(ValueError):self.store.study_time_settings(self.path,0)

    def test_calibration_is_course_specific_and_requires_real_completed_samples(self):
        self.prepare();content=self.content();content['blocks']=[{'id':'r'+str(i),'kind':'text','text':'Word '*150,'sources':[self.source]} for i in range(4)]
        self.store._save_chapter(self.path,'pram',content);self.store.course_select(self.sid,'pram',version=2)
        end=time.time()*1000-300000
        for i in range(3):
            self.record(id='sample'+str(i),block='r'+str(i),version=2,started=end+i*40000,ended=end+i*40000+30000)
            self.mark(block='r'+str(i),version=2)
        result=self.estimate();self.assertEqual(result['calibration']['reading']['samples'],3)
        self.assertLess(result['calibration']['reading']['factor'],1)
        self.assertEqual(self.store._time_calibration('another-course'),{})
        # Neither marks nor timing become messages or tutor-context fields.
        self.assertNotIn('study_time',self.store.course_context(self.sid))

    def test_wrong_sessions_blocks_and_recall_are_rejected(self):
        self.prepare()
        with self.assertRaises(ValueError):self.store.study_time_mark(self.sid,'missing',1,'intro','studied')
        with self.assertRaises(ValueError):self.store.study_time_mark(self.sid,'pram',1,'intro','mastered')
        with self.store.db:self.store.db.execute('INSERT INTO course_recall_runs VALUES(?,?,?,0)',(self.sid,'pram','activity'))
        with self.assertRaises(ValueError):self.mark()
        with self.assertRaises(ValueError):self.record()
        with self.assertRaises(ValueError):self.store.course_study_time(self.path,'wrong-session')

    def test_non_technical_course_has_independent_forecasts_and_defaults(self):
        other='literature-2026';folder=self.root/'corsi'/other/'materiali';folder.mkdir(parents=True)
        doc=fixtures.pymupdf.open();page=doc.new_page();page.insert_text((30,40),'Reading a novel: interpretation, argument and textual evidence.');doc.save(folder/'notes.pdf');doc.close()
        self.store.import_course(other);p=self.store.course_create(other,engine=1,request='Interpretazione e scrittura')['id']
        data={'chapters':[{'id':'essay','title':'Interpretazione narrativa','objective':'Leggere criticamente e formulare una tesi','assessment':'Argomentare con esempi testuali','exam_skills':['Interpretare','Scrivere','Rivedere'],'prerequisites':[]}]}
        with self.store.db:self.store.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)',(p,1,pack(data),'Fixture indipendente',stamp()))
        estimate=self.store.course_study_time(p)
        self.assertEqual(estimate['forecast_chapters'],1);self.assertGreater(estimate['total']['low'],0)
        self.assertEqual(estimate['calibration'],{});self.assertEqual(estimate['daily_minutes'],30)
        self.assertEqual(estimate['forecast_basis_chapters'],0)

    def test_forecast_is_replaced_when_content_is_published(self):
        self.prepare();plan=self.store._plan(self.path);data=copy.deepcopy(plan['data'])
        data['chapters'].append(dict(data['chapters'][0],id='future',title='Future topic',prerequisites=['pram']))
        with self.store.db:self.store.db.execute('INSERT INTO course_plans VALUES(?,?,?,?,?)',(self.path,plan['version']+1,pack(data),'Future chapter',stamp()))
        before=self.estimate();self.assertEqual(before['chapters'][1]['basis'],'plan')
        self.store._save_chapter(self.path,'future',{'blocks':[{'id':'future-text','kind':'text','text':'A concise explanation of the next topic.','sources':[self.source]}]})
        after=self.estimate();self.assertEqual(after['chapters'][1]['basis'],'content');self.assertEqual(after['forecast_chapters'],0)
        self.assertNotEqual(before['chapters'][1]['total'],after['chapters'][1]['total'])

    def test_cache_tracks_each_grade_instead_of_only_the_number_of_errors(self):
        self.prepare();content=self.content();second=copy.deepcopy(content['blocks'][1]);second['id']='practice2';second['spec']=dict(second['spec'],kind='open',prompt='Explain all the reasoning.',answer=None)
        content['blocks'].append(second);self.store._save_chapter(self.path,'pram',content);self.store.course_select(self.sid,'pram',version=2)
        rows=self.store.db.execute('SELECT activity,activity_version FROM course_chapter_activities WHERE session=? AND version=2 ORDER BY block',(self.sid,)).fetchall()
        ids=[]
        for i,row in enumerate(rows):ids.append(self.store.event(self.sid,row[0],row[1],'cache-attempt-'+str(i),'submit',{'answer':1})['attempt']['id'])
        with self.store.db:
            for aid,correct in zip(ids,[False,True]):self.store.db.execute('UPDATE attempts SET grade=? WHERE id=?',(pack({'correct':correct}),aid))
        first=self.estimate()
        with self.store.db:
            for aid,correct in zip(ids,[True,False]):self.store.db.execute('UPDATE attempts SET grade=? WHERE id=?',(pack({'correct':correct}),aid))
        second=self.estimate();self.assertNotEqual(first['remaining'],second['remaining'])
