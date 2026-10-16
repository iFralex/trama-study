import asyncio
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from polimi_lectures.alignment import align_course, child
from polimi_lectures.cli import parser
from polimi_lectures.core import DownloadError, slug


class CatalogStub:
    def __init__(self,root):
        self.root=root
        self.course='123456 - SYSTEM ARCHITECTURES (DOCENTE) [2024-25]'
        self.data=[{'id':'aabbcc','course':self.course,'date':'2024-09-01','title':'Prima'},
                   {'id':'ddeeff','course':self.course,'date':'2024-09-02','title':'Seconda'}]
        (root/'corsi'/slug(self.course)/'materiali').mkdir(parents=True)
        for row in self.data:
            self.folder(row).mkdir(parents=True)
            (self.folder(row)/'video.mp4').write_bytes(b'video-placeholder')
    def rows(self,course=None): return self.data
    def folder(self,row): return self.root/'corsi'/slug(self.course)/row['id']


class AlignmentUI(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory()
        self.root=Path(self.temp.name)
        self.catalog=CatalogStub(self.root)

    async def asyncTearDown(self): self.temp.cleanup()

    async def execute(self,**kwargs):
        with patch('polimi_lectures.transcribe.select_local_course',new=AsyncMock(return_value=self.catalog.course)) as select, \
             patch('polimi_lectures.alignment.ensure_runtime',new=AsyncMock(return_value=Path('/fake/python'))) as runtime, \
             patch('polimi_lectures.alignment.child',new=AsyncMock(return_value=0)) as process:
            code=await align_course(self.catalog,'system architectures',**kwargs)
        self.assertEqual(code,0)
        select.assert_awaited_once_with(self.catalog,'system architectures',purpose='analizzare')
        request=next((self.root/'.state/slides-jobs').glob('*.json'))
        return json.loads(request.read_text()),process

    async def test_generic_course_and_all_lessons_offline(self):
        request,process=await self.execute(all_pending=True)
        self.assertEqual(len(request['items']),2)
        self.assertIn('SYSTEM-ARCHITECTURES',request['materials'])
        self.assertTrue(all(i['output'].endswith('/allineamento') for i in request['items']))
        self.assertEqual(process.await_args.args[0][2],'polimi_lectures.slide_worker')

    async def test_selection_interval_keeps_full_output_separate(self):
        request,_=await self.execute(lesson_id='dd',start=1200,end=1900)
        self.assertEqual(len(request['items']),1)
        self.assertIn('ddeeff',request['items'][0]['video'])
        self.assertIn('/allineamento/prove/',request['items'][0]['output'])
        self.assertEqual(request['options']['start'],1200)

    async def test_interactive_trial_and_index_only(self):
        with patch('polimi_lectures.alignment.ask',new=AsyncMock(return_value='2')):
            request,_=await self.execute()
        self.assertEqual(len(request['items']),1)

    async def test_invalid_lesson_does_not_start_worker(self):
        with patch('polimi_lectures.transcribe.select_local_course',new=AsyncMock(return_value=self.catalog.course)), \
             patch('polimi_lectures.alignment.ensure_runtime',new=AsyncMock()) as runtime:
            with self.assertRaises(DownloadError):
                await align_course(self.catalog,'system architectures',lesson_id='unknown')
            runtime.assert_not_called()

    async def test_child_cancel_terminates_worker(self):
        process=AsyncMock()
        process.returncode=None
        process.terminate=lambda: setattr(process,'returncode',-15)
        process.wait.side_effect=[asyncio.CancelledError(),-15]
        with patch('asyncio.create_subprocess_exec',new=AsyncMock(return_value=process)):
            with self.assertRaises(asyncio.CancelledError): await child(['/fake/python'])
        self.assertEqual(process.returncode,-15)

    def test_parser(self):
        args=parser().parse_args(['align','--course','system architectures','--all','--crop','10','20','800','600','--pdf','slide.pdf'])
        self.assertTrue(args.all_pending)
        self.assertEqual(args.crop,[10,20,800,600])
        self.assertEqual(args.pdf_filter,['slide.pdf'])


if __name__=='__main__': unittest.main()
