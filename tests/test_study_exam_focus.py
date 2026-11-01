import copy
import json
import unittest
from tests import test_study as fixtures
from tests import test_study_preparation as prep


@unittest.skipIf(fixtures.pymupdf is None, 'Requires native slides runtime')
class ExamFocusTest(unittest.TestCase):
    setUp = fixtures.StudyTest.setUp
    tearDown = fixtures.StudyTest.tearDown
    start = prep.PreparationTest.start
    task = prep.PreparationTest.task
    commit = prep.PreparationTest.commit
    read = prep.PreparationTest.read
    blueprint = prep.PreparationTest.blueprint
    to_chapter = prep.PreparationTest.to_chapter
    content = prep.PreparationTest.content

    def focused_task(self):
        self.to_chapter()
        self.store.setting('exam_focus_enabled', True)
        task = self.task()
        self.assertEqual(task['exam_policy']['version'], 1)
        self.assertNotIn('profile', task)
        self.store.preparation_begin(self.path, task)
        return task

    def outline(self, task, role='exam'):
        refs = [task['exam_policy']['questions'][0]['id']] if role in ('exam', 'foundation') else []
        focus = {'role': role, 'exam_refs': refs, 'reason': 'Necessario per distinguere accessi concorrenti.'}
        rows = [{'id': 'intro', 'kind': 'text', 'role': 'explain', 'focus': focus, 'depends_on': []}]
        if role in ('exam', 'foundation'):
            rows += [{'id': 'worked', 'kind': 'text', 'role': 'worked', 'focus': focus, 'depends_on': ['intro']},
                     {'id': 'exercise', 'kind': 'activity', 'role': 'independent', 'focus': focus, 'depends_on': ['intro', 'worked']}]
        return rows

    def blocks(self, task):
        content = self.content()['blocks']
        intro = content[0]
        worked = dict(intro, id='worked', text='Esempio completo con accessi distinti.')
        exercise = content[1]
        exercise['spec'].update(kind='open', origin='adapted', prompt='Classifica accessi nel nuovo scenario e motiva.', exam_variant={'question': task['exam_policy']['questions'][0]['id'], 'adaptation': 'Nuovi accessi, stessa richiesta di classificazione motivata.'})
        exercise['spec'].pop('verification', None)
        return [intro, worked, exercise]

    def test_packets_use_verified_unreserved_exam_questions_and_keep_their_identity(self):
        task = self.focused_task()
        questions = task['exam_policy']['questions']
        self.assertTrue(questions)
        self.assertLessEqual(len(questions), 8)
        for q in questions:
            original = json.loads(self.store.db.execute('SELECT data FROM course_questions WHERE path=? AND id=?', (self.path, q['id'])).fetchone()[0])
            self.assertEqual(original['text'], q['text'])
            self.assertTrue(original['authenticity_verified'])
            self.assertTrue(original['in_scope'])
            for ref in q['sources']:
                self.assertFalse(self.store.source(ref, allow_solutions=False)['reserved'])
        ref = questions[0]['sources'][0]
        with self.store.db:
            self.store.db.execute('UPDATE passages SET reserved=1 WHERE id=?', (ref,))
        self.assertFalse(self.store._exam_focus_questions(self.path))

    def test_complementary_sections_need_no_exercises_and_survive_commit_and_review(self):
        task = self.focused_task();rows = self.outline(task, 'support')
        blocks = self.content()['blocks'][:1]
        saved = self.store.preparation_chapter_checkpoint(self.path, task['task_id'], {'version': 1, 'outline': rows, 'blocks': blocks})
        self.assertEqual(saved['blocks'][0]['focus']['role'], 'support')
        self.store.preparation_commit(self.path, task, {'blocks': saved['blocks']})
        review = self.task()
        self.assertEqual(review['kind'], 'review_solve')
        self.assertEqual(review['exam_policy']['questions'], [])
        self.assertEqual(review['draft']['exam_focus_version'], 1)
        self.store.preparation_begin(self.path, review)
        self.store.preparation_commit(self.path, review, {'solutions': []})
        self.assertEqual(self.task()['kind'], 'review_discipline')

    def test_exam_variants_keep_references_and_cannot_become_multiple_choice(self):
        task = self.focused_task();rows = self.outline(task);blocks = self.blocks(task)
        bad = copy.deepcopy(blocks);bad[-1]['spec']['kind'] = 'choice'
        with self.assertRaisesRegex(ValueError, 'formato'):
            self.store.preparation_chapter_checkpoint(self.path, task['task_id'], {'version': 1, 'outline': rows, 'blocks': bad})
        saved = self.store.preparation_chapter_checkpoint(self.path, task['task_id'], {'version': 1, 'outline': rows, 'blocks': blocks})
        self.assertEqual(saved['blocks'][-1]['focus']['references'][0]['question'], task['exam_policy']['questions'][0]['id'])
        self.store.preparation_commit(self.path, task, {'blocks': saved['blocks']})
        view = self.store.course_path_view(self.path)
        self.assertFalse(view['chapters'][0]['ready'], 'Normal independent and disciplinary reviews still apply')
        self.assertEqual(self.task()['exam_policy']['questions'][0]['id'], task['exam_policy']['questions'][0]['id'])

    def test_foundations_retain_practice_and_support_cannot_claim_exam_evidence(self):
        task = self.focused_task();rows = self.outline(task, 'foundation');blocks = self.blocks(task)
        blocks[-1]['spec']['origin'] = 'generated';blocks[-1]['spec'].pop('exam_variant')
        saved = self.store.preparation_chapter_checkpoint(self.path, task['task_id'], {'version': 1, 'outline': rows, 'blocks': blocks})
        self.assertEqual(saved['blocks'][-1]['focus']['role'], 'foundation')
        bad = copy.deepcopy(rows);bad[0]['focus'] = dict(bad[0]['focus'], role='support')
        with self.assertRaisesRegex(ValueError, 'Complementare'):
            self.store.preparation_chapter_checkpoint(self.path, task['task_id'], {'version': 1, 'outline': bad, 'blocks': blocks})

    def test_complementary_exercises_fake_evidence_and_forward_dependencies_are_rejected(self):
        task = self.focused_task();rows = self.outline(task);blocks = self.blocks(task)
        for change, message in [('support', 'Complementare'), ('fake', 'non verificato'), ('future', 'precedenti')]:
            bad = copy.deepcopy(rows)
            if change == 'support':bad[-1]['focus'] = {'role': 'support', 'exam_refs': [], 'reason': 'Complementare'}
            elif change == 'fake':bad[-1]['focus']['exam_refs'] = ['invented-question']
            else:bad[0]['depends_on'] = ['exercise']
            with self.subTest(change=change), self.assertRaisesRegex(ValueError, message):
                self.store.preparation_chapter_checkpoint(self.path, task['task_id'], {'version': 1, 'outline': bad, 'blocks': blocks})

    def test_legacy_checkpoint_is_resumed_without_new_policy_or_rewriting_content(self):
        task = self.to_chapter();self.store.preparation_begin(self.path, task)
        blocks = self.content()['blocks'];blocks.insert(1, dict(blocks[0], id='worked'))
        rows = [{'id': b['id'], 'kind': b['kind']} for b in blocks]
        self.store.preparation_chapter_checkpoint(self.path, task['task_id'], {'version': 1, 'outline': rows, 'blocks': blocks[:1]})
        self.store.setting('exam_focus_enabled', True)
        resumed = self.task()
        self.assertEqual(resumed, task)
        self.assertNotIn('exam_policy', resumed)
        self.assertEqual(self.store._chapter_recovery(self.path, resumed)['blocks'], blocks[:1])

    def test_additional_questions_retrieved_on_demand_are_checked_against_the_verified_bank(self):
        task = self.focused_task();q = task['exam_policy']['questions'][0]
        # A second verified record can belong to the same historical question family.
        original = json.loads(self.store.db.execute('SELECT data FROM course_questions WHERE path=? AND id=?', (self.path, q['id'])).fetchone()[0])
        document = self.store.source(q['sources'][0])['document'];extra_id = 'a' * 24
        with self.store.db:
            self.store.db.execute('INSERT INTO course_questions VALUES(?,?,?,?)', (self.path, extra_id, document, json.dumps(original)))
        profile = self.store.course_exam_profile(self.path, limit=40)
        self.assertIn(extra_id, [item['id'] for item in profile['questions']])
        rows = self.outline(task);blocks = self.blocks(task)
        for row in rows:row['focus'] = dict(row['focus'], exam_refs=[extra_id])
        blocks[-1]['spec']['exam_variant']['question'] = extra_id
        saved = self.store.preparation_chapter_checkpoint(self.path, task['task_id'], {'version': 1, 'outline': rows, 'blocks': blocks})
        self.assertEqual(saved['blocks'][0]['focus']['references'][0]['question'], extra_id)

    def test_new_policy_recovery_preserves_labels_and_validated_completed_sections(self):
        task = self.focused_task();rows = self.outline(task);blocks = self.blocks(task)
        first = self.store.preparation_chapter_checkpoint(self.path, task['task_id'], {'version': 1, 'outline': rows, 'blocks': blocks[:1]})
        self.store.preparation_model_call(self.path, task['task_id'], 'interrupted', {'provider': 'test', 'id': 'model'}, 'author', {'protocol': 'chapter-batches-1', 'output': json.dumps({'blocks': blocks[1:2]})})
        recovered = self.store._chapter_recovery(self.path, task)
        self.assertEqual(recovered['error'], '')
        self.assertEqual(len(recovered['blocks']), 2)
        self.assertEqual(recovered['blocks'][0], first['blocks'][0])
        self.assertEqual(recovered['blocks'][1]['focus']['role'], 'exam')
