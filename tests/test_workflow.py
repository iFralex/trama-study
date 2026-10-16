import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from polimi_lectures.core import Catalog
from polimi_lectures.workflow import course_workflow, delete_test_video


URL='https://politecnicomilano.webex.com/recordingservice/sites/politecnicomilano/recording/playback/11111111111111111111111111111111'


class TestDeletionTests(unittest.TestCase):
    def test_deleting_trial_keeps_notes_materials_and_catalog_entry(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog = Catalog(folder)
            catalog.add('Parallel Computing', URL, 'Trial')
            row = catalog.rows()[0]
            target = catalog.folder(row)
            target.mkdir(parents=True)
            (target/'video.mp4').write_bytes(b'video')
            (target/'metadata.json').write_text('{}')
            (target/'notes.md').write_text('Keep')
            catalog.update(row, 'complete', target.relative_to(folder))
            self.assertEqual(delete_test_video(catalog, [row]), 1)
            self.assertFalse((target/'video.mp4').exists())
            self.assertEqual((target/'notes.md').read_text(), 'Keep')
            self.assertEqual(catalog.rows()[0]['status'], 'pending')
            catalog.db.close()


class WorkflowTests(unittest.IsolatedAsyncioTestCase):
    async def test_trial_menu_allows_delete_then_continue_without_relaunch(self):
        with tempfile.TemporaryDirectory() as folder:
            catalog=Catalog(folder)
            catalog.add('Parallel Computing',URL,'Trial')
            row=catalog.rows()[0]
            target=catalog.folder(row)
            target.mkdir(parents=True)
            (target/'video.mp4').write_bytes(b'video')
            calls=[]
            async def collect(context, catalog, query, state):
                calls.append(state)
                state.update(action='recordings',test=True,course={'label':'Parallel Computing','url':'fixture'})
                return [row] if len(calls)==1 else []
            with patch('polimi_lectures.workflow.guided',new=collect), \
                 patch('polimi_lectures.workflow.download_rows',new=AsyncMock(return_value=0)), \
                 patch('polimi_lectures.workflow.ask',new=AsyncMock(side_effect=['3','1','q'])):
                result=await course_workflow(object(),catalog,'Parallel Computing')
            self.assertEqual(result,0)
            self.assertEqual(len(calls),2)
            self.assertIs(calls[0],calls[1])
            self.assertFalse((target/'video.mp4').exists())
            catalog.db.close()
