"""New tutor conversations preserve work without copying assessment evidence."""
import json
import unittest
from tests import test_study as fixtures
from tests import test_study_course as course_fixtures


@unittest.skipIf(fixtures.pymupdf is None, 'Requires native slides runtime')
class LearningContinuityTest(unittest.TestCase):
    setUp = fixtures.StudyTest.setUp
    tearDown = fixtures.StudyTest.tearDown
    start = course_fixtures.CourseTest.start
    blueprint = course_fixtures.CourseTest.blueprint
    read_all = course_fixtures.CourseTest.read_all
    content = course_fixtures.CourseTest.content
    prepare = course_fixtures.CourseTest.prepare

    def submit(self, answer='1'):
        activity = self.store.view(self.sid)['activities'][0]
        attempt = self.store.event(self.sid, activity['id'], 1, 'original-submit', 'submit', {'answer': answer})['attempt']
        self.store.assess(self.sid, attempt['id'], {'correct': True, 'feedback': 'Giudizio originale salvato.', 'rubric': 'Criteri originali'})
        return activity, attempt['id']

    def test_new_conversation_recovers_submitted_answer_and_grade_without_new_evidence(self):
        self.prepare();old, aid = self.submit()
        self.store.message(self.sid, 'user', 'Spiegami questo tentativo')
        before = [tuple(r) for r in self.store.db.execute('SELECT * FROM attempts')]
        fresh = self.store.course_open(self.path, fresh=True)
        current = fresh['activities'][0];sid = fresh['session']['id']
        self.assertNotEqual(sid, self.sid);self.assertNotEqual(current['id'], old['id'])
        self.assertEqual(current['state']['answer'], '1');self.assertEqual(fresh['messages'], [])
        self.assertEqual(len(fresh['attempts']), 1)
        attempt = fresh['attempts'][0]
        self.assertEqual((attempt['id'], attempt['activity'], attempt['source_activity']), (aid, current['id'], old['id']))
        self.assertEqual(attempt['grade']['feedback'], 'Giudizio originale salvato.')
        self.assertEqual([tuple(r) for r in self.store.db.execute('SELECT * FROM attempts')], before)
        # Explanations and corrections resolve the original attempt rather than grading again.
        assessment = self.store.assessment(sid, aid)
        self.assertEqual(assessment['attempt']['session'], self.sid)
        self.assertEqual(assessment['activity']['id'], old['id'])
        self.store.correct(sid, aid, 'Una contestazione')
        self.assertEqual(self.store.assessment(self.sid, aid)['attempt']['correction'], 'Una contestazione')
        self.assertEqual(len(self.store.view(sid)['attempts']), 1)

    def test_chain_of_new_conversations_keeps_one_attempt_and_latest_draft(self):
        self.prepare();_, aid = self.submit()
        second = self.store.course_open(self.path, fresh=True);activity = second['activities'][0]
        self.store.event(second['session']['id'], activity['id'], 1, 'new-draft', 'change', {'answer': 'Ragionamento rivisto'})
        third = self.store.course_open(self.path, fresh=True)
        self.assertEqual(third['activities'][0]['state']['answer'], 'Ragionamento rivisto')
        self.assertEqual([a['id'] for a in third['attempts']], [aid])
        self.assertEqual(self.store.view(self.sid)['activities'][0]['state']['answer'], '1')

    def test_explicit_reset_and_own_edits_are_preserved(self):
        self.prepare();old, _ = self.submit()
        fresh = self.store.course_open(self.path, fresh=True);sid = fresh['session']['id'];new = fresh['activities'][0]
        self.store.event(sid, new['id'], 1, 'clear', 'reset', {})
        self.assertEqual(self.store.view(sid)['activities'][0]['state'], {})
        self.store.event(sid, new['id'], 1, 'own-edit', 'change', {'answer': 'Nuova bozza'})
        self.store.event(self.sid, old['id'], 1, 'later-edit', 'change', {'answer': 'Modifica nella vecchia chat'})
        self.assertEqual(self.store.view(sid)['activities'][0]['state']['answer'], 'Nuova bozza')

    def test_hints_are_not_erased_by_new_conversation_and_recalls_are_idempotent(self):
        self.prepare();old, aid = self.submit()
        self.store.event(self.sid, old['id'], 1, 'help', 'hint', {})
        self.store.course_recall_card(self.sid, aid, {'due': '2026-12-01'})
        fresh = self.store.course_open(self.path, fresh=True);sid = fresh['session']['id'];new = fresh['activities'][0]
        self.assertTrue(self.store.course_recall_card(sid, aid)['duplicate'])
        attempt = self.store.event(sid, new['id'], 1, 'retry', 'submit', {'answer': '1'})['attempt']
        self.assertEqual(attempt['aids'], 1)
        self.assertEqual(len(self.store.course_recalls(self.path)), 1)
        self.assertEqual(len(self.store.view(sid)['attempts']), 2)

    def test_other_paths_and_exam_sessions_cannot_access_attempt(self):
        self.prepare();_, aid = self.submit()
        other = self.store.course_create(self.course, engine=1, request='Altro percorso')['id']
        other_sid = self.store.course_path_view(other)['sid']
        for sid in [other_sid, self.store.open_session(self.course, mode='exam', fresh=True)['session']['id']]:
            with self.assertRaises(ValueError):self.store.assessment(sid, aid)
            with self.assertRaises(ValueError):self.store.assess(sid, aid, {'correct': False})
            with self.assertRaises(ValueError):self.store.correct(sid, aid, 'Non autorizzato')

    def test_changed_exercise_and_chapter_version_do_not_inherit(self):
        self.prepare();_, aid = self.submit()
        fresh = self.store.course_open(self.path, fresh=True);sid = fresh['session']['id'];new = fresh['activities'][0]
        # Even an identical prompt with different grading criteria is a distinct exercise.
        raw = self.store.db.execute('SELECT spec FROM activities WHERE id=?', (new['id'],)).fetchone()[0]
        spec = json.loads(raw);spec['rubric'] = 'Criteri diversi'
        with self.store.db:self.store.db.execute('UPDATE activities SET spec=? WHERE id=?', (json.dumps(spec), new['id']))
        self.assertEqual(self.store.view(sid)['attempts'], [])
        self.assertEqual(self.store.view(sid)['activities'][0]['state'], {})
        with self.assertRaises(ValueError):self.store.assessment(sid, aid)
        content = self.content();content['blocks'][1]['spec']['answer'] = 2
        self.store._save_chapter(self.path, 'pram', content)
        self.store.course_select(sid, 'pram', version=2)
        revised = self.store.course_open(self.path, sid=sid, fresh=True)
        self.assertEqual(revised['activities'][0]['state'], {})
        self.assertEqual(revised['attempts'], [])
        with self.assertRaises(ValueError):self.store.assessment(revised['session']['id'], aid)
