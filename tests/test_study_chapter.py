import copy
import json
import unittest
from tests import test_study as fixtures
from tests import test_study_preparation as prep
from polimi_lectures.study_chapter import recover_chapter_blocks

class RecoveryParserTest(unittest.TestCase):
    def test_only_complete_array_items_are_recovered(self):
        blocks=[{'id':'a','kind':'text','text':'Quoted \\" braces } [ and Unicode ∧','sources':['s']},{'id':'b','kind':'text','text':'Complete','sources':['s']}]
        full=json.dumps({'blocks':blocks},ensure_ascii=False)
        self.assertEqual(recover_chapter_blocks(full),blocks)
        start=full.index('{"id": "b"')
        self.assertEqual(recover_chapter_blocks(full[:start+20]),blocks[:1])
        self.assertEqual(recover_chapter_blocks('```json\n'+full),blocks)
        self.assertEqual(recover_chapter_blocks('{"blocks":[{"id":"unfinished'),[])
        self.assertEqual(recover_chapter_blocks('not JSON '+full),[])
        self.assertEqual(recover_chapter_blocks('{"note":"x","blocks":'+json.dumps(blocks)+'}'),blocks)

@unittest.skipIf(fixtures.pymupdf is None,'Requires native slides runtime')
class ChapterCheckpointTest(unittest.TestCase):
    setUp=fixtures.StudyTest.setUp
    tearDown=fixtures.StudyTest.tearDown
    start=prep.PreparationTest.start
    task=prep.PreparationTest.task
    commit=prep.PreparationTest.commit
    read=prep.PreparationTest.read
    blueprint=prep.PreparationTest.blueprint
    to_chapter=prep.PreparationTest.to_chapter
    content=prep.PreparationTest.content

    def setup_task(self):
        task=self.to_chapter();self.store.preparation_begin(self.path,task)
        blocks=self.content()['blocks'];blocks.insert(1,dict(blocks[0],id='worked',text='Complete worked example.'))
        outline=[{'id':b['id'],'kind':b['kind']} for b in blocks]
        return task,blocks,outline

    def test_legacy_partial_recovery_is_saved_without_publishing(self):
        task,blocks,outline=self.setup_task()
        partial='{"blocks":['+json.dumps(blocks[0])+','+json.dumps(blocks[1])+',{"id":"unfinished'
        self.store.preparation_model_call(self.path,task['task_id'],'call',{'provider':'test','id':'model'},'author',{'output':partial})
        recovered=self.store.preparation_begin(self.path,task)['chapter_recovery']
        self.assertEqual(recovered['blocks'],blocks[:2]);self.assertEqual(recovered['error'],'')
        self.assertIsNone(self.store._chapter(self.path,task['chapter']['id']))
        saved=self.store.preparation_chapter_checkpoint(self.path,task['task_id'],{'version':1,'outline':outline,'blocks':blocks[:2]})
        self.assertEqual(saved['blocks'],blocks[:2])
        self.assertEqual(self.store.preparation_progress(self.path)['current_task']['chapter_progress'],{'done':2,'total':3})

    def test_sources_and_complete_deterministic_checks_are_still_mandatory(self):
        task,blocks,outline=self.setup_task();bad=copy.deepcopy(blocks);bad[0]['sources']=['unread']
        with self.assertRaises(ValueError):self.store.preparation_chapter_checkpoint(self.path,task['task_id'],{'version':1,'outline':outline,'blocks':bad})
        bad=copy.deepcopy(blocks);bad[-1]['spec']['verification']['expected']=999
        with self.assertRaises(ValueError):self.store.preparation_chapter_checkpoint(self.path,task['task_id'],{'version':1,'outline':outline,'blocks':bad})
        self.assertIsNone(self.store._chapter(self.path,task['chapter']['id']))

    def test_verified_web_refs_and_unambiguous_scaling_aliases_keep_all_text(self):
        task,blocks,outline=self.setup_task();url='https://example.org/primary'
        self.store.preparation_read(task['task_id'],{'url':url,'text':'Primary source read'},'read_web_page')
        blocks[0]['sources'].append(url);text=blocks[0]['text']
        blocks[-1]['spec']['answer']=1/(.1+.9/8)
        blocks[-1]['spec']['verification']={'model':'amdahl','input':{'p':8,'serial_fraction':.1,'parallel_fraction':.9},'expected':1/(.1+.9/8)}
        saved=self.store.preparation_chapter_checkpoint(self.path,task['task_id'],{'version':1,'outline':outline,'blocks':blocks})
        self.assertEqual(saved['blocks'][0]['text'],text);self.assertEqual(saved['blocks'][0]['external_sources'],[url]);self.assertNotIn(url,saved['blocks'][0]['sources'])
        self.assertEqual(saved['blocks'][-1]['spec']['verification']['input']['fraction'],.9)
        blocks[-1]['spec']['verification']['input']['processors']=4
        with self.assertRaisesRegex(ValueError,'discordanti'):self.store.preparation_chapter_checkpoint(self.path,task['task_id'],{'version':1,'outline':outline,'blocks':blocks})

    def test_truncated_new_batch_can_extend_only_the_expected_outline_prefix(self):
        task,blocks,outline=self.setup_task()
        self.store.preparation_chapter_checkpoint(self.path,task['task_id'],{'version':1,'outline':outline,'blocks':blocks[:1]})
        self.store.preparation_model_call(self.path,task['task_id'],'partial',{'provider':'test','id':'model'},'author',{'protocol':'chapter-batches-1','error':'timeout','output':'{"blocks":['+json.dumps(blocks[1])+',{"id":"unfinished'})
        result=self.store._chapter_recovery(self.path,task);self.assertEqual(result['blocks'],blocks[:2]);self.assertEqual(result['error'],'')
        self.assertIsNone(self.store._chapter(self.path,task['chapter']['id']))

    def test_existing_checkpoint_cannot_be_rewritten_or_rolled_back(self):
        task,blocks,outline=self.setup_task()
        self.store.preparation_chapter_checkpoint(self.path,task['task_id'],{'version':1,'outline':outline,'blocks':blocks[:2]})
        changed=copy.deepcopy(blocks);changed[0]['text']='Unexpected rewrite'
        with self.assertRaisesRegex(ValueError,'Conserva i blocchi'):
            self.store.preparation_chapter_checkpoint(self.path,task['task_id'],{'version':1,'outline':outline,'blocks':changed})
        with self.assertRaisesRegex(ValueError,'Conserva i blocchi'):
            self.store.preparation_chapter_checkpoint(self.path,task['task_id'],{'version':1,'outline':outline,'blocks':blocks[:1]})
        saved=self.store.preparation_chapter_checkpoint(self.path,task['task_id'],{'version':1,'outline':outline,'blocks':blocks})
        visible=copy.deepcopy(saved['blocks']);visible[-1]['spec']['verification'].pop('status',None)
        self.assertEqual(visible,blocks)
        self.assertEqual(saved['blocks'][-1]['spec']['verification']['status'],'checked_for_declared_model')
        self.store.preparation_commit(self.path,task,{'blocks':saved['blocks']})
        self.assertIsNone(self.store._chapter(self.path,task['chapter']['id']),'Full chapter remains a draft until independent reviews')
        self.assertEqual(self.task()['kind'],'review_solve')
