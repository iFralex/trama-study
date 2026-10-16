import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from playwright.async_api import async_playwright

from polimi_lectures.materials import discover_materials, save_material, selection_numbers


class MaterialDownloadTests(unittest.TestCase):
    def test_file_selection_ranges_are_bounded(self):
        self.assertEqual(selection_numbers('1,3,5-7', 7), [0, 2, 4, 5, 6])
        for value in ('0', '2-8', '3-1', '../file'):
            with self.assertRaises(ValueError):
                selection_numbers(value, 7)

    def test_nested_files_and_conditional_download_are_preserved(self):
        requests = []
        payload = b'%PDF-1.7 fixture'
        def respond(request):
            requests.append(request)
            if request.headers.get('if-none-match') == '"v1"':
                return httpx.Response(304)
            return httpx.Response(200, headers={'content-type': 'application/pdf', 'content-length': str(len(payload)), 'etag': '"v1"'}, content=payload)
        asset = {'kind': 'file', 'url': 'https://webeep.polimi.it/pluginfile.php/1/mod_folder/content/0/week1/intro.pdf',
                 'name': 'intro.pdf', 'group': 'Course lectures', 'module_id': '10', 'relative': 'week1/intro.pdf'}
        with tempfile.TemporaryDirectory() as folder, httpx.Client(transport=httpx.MockTransport(respond)) as client:
            base, index = Path(folder), {}
            self.assertEqual(save_material(client, asset, base, index), 'downloaded')
            target = base / next(iter(index.values()))['path']
            self.assertEqual(target.read_bytes(), payload)
            self.assertEqual(target.parent.name, 'week1')
            self.assertEqual(save_material(client, asset, base, index), 'present')
            self.assertEqual(len(requests), 2)

    def test_resource_uses_server_filename_and_rejects_login_html(self):
        asset = {'kind': 'file', 'url': 'https://webeep.polimi.it/mod/resource/view.php?id=99&redirect=1',
                 'name': 'Slides', 'group': 'Slides', 'module_id': '99', 'relative': None}
        def file(request):
            return httpx.Response(200, headers={'content-type': 'application/pdf', 'content-disposition': 'attachment; filename="lecture.pdf"'}, content=b'%PDF-fixture')
        with tempfile.TemporaryDirectory() as folder, httpx.Client(transport=httpx.MockTransport(file)) as client:
            index = {}
            self.assertEqual(save_material(client, asset, Path(folder), index), 'downloaded')
            self.assertTrue(next(Path(folder).rglob('lecture.pdf')).exists())
        def login(request):
            return httpx.Response(200, headers={'content-type': 'text/html'}, content=b'<form>login</form>')
        from polimi_lectures.core import DownloadError
        with tempfile.TemporaryDirectory() as folder, httpx.Client(transport=httpx.MockTransport(login)) as client:
            with self.assertRaises(DownloadError):
                save_material(client, asset, Path(folder), {})


class MaterialDiscoveryTests(unittest.IsolatedAsyncioTestCase):
    async def test_course_cards_are_opened_before_collecting_materials(self):
        async with async_playwright() as pw:
            if not Path(pw.chromium.executable_path).exists():
                self.skipTest('Chromium non installato')
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context()
            visited = []
            async def respond(route):
                url = route.request.url
                visited.append(url)
                if '/course/view.php' in url:
                    body = '''<aside><a href="/mod/folder/view.php?id=999">Altro corso</a></aside>
                        <main id="region-main"><a href="/course/section.php?id=71">Materiali</a>
                        <a href="/course/section.php?id=71">Materiali</a>
                        <a href="/course/view.php?id=42&section=2">Documenti</a>
                        <a href="/course/view.php?id=99&section=2">Altro corso</a>
                        <a href="/pluginfile.php/1/mod_label/intro/program.pdf">Programma</a>
                        <a href="/pluginfile.php/1/mod_label/intro/logo.png">Logo</a></main>'''
                    if 'section=2' in url:
                        body = '<main><a href="/mod/resource/view.php?id=13">Documento</a></main>'
                elif '/course/section.php' in url:
                    body = '<main><a href="/mod/folder/view.php?id=10">Slides</a></main>'
                elif '/mod/folder/' in url:
                    body = '<main><a href="/pluginfile.php/1/mod_folder/content/0/week1/intro.pdf">intro.pdf</a></main>'
                else:
                    raise AssertionError('Navigazione imprevista: ' + url)
                await route.fulfill(content_type='text/html', body=body)
            await context.route('**/*', respond)
            try:
                assets = await discover_materials(context, {'url': 'https://webeep.polimi.it/course/view.php?id=42', 'label': 'Un corso qualsiasi'})
                self.assertEqual(len(assets), 3)
                self.assertEqual(sum('/course/section.php?id=71' in u for u in visited), 1)
                self.assertFalse(any('id=999' in u or 'id=99&' in u for u in visited))
                self.assertTrue(any(a['name'] == 'program.pdf' for a in assets))
                self.assertTrue(any(a['relative'] == 'week1/intro.pdf' for a in assets))
                self.assertTrue(any('/mod/resource/' in a['url'] for a in assets))
            finally:
                await browser.close()

    async def test_folders_files_and_page_are_collected_with_course_session(self):
        async with async_playwright() as pw:
            if not Path(pw.chromium.executable_path).exists():
                self.skipTest('Chromium non installato')
            browser = await pw.chromium.launch(headless=True)
            context = await browser.new_context()
            async def respond(route):
                url = route.request.url
                if '/course/view.php' in url:
                    body = '<main><a href="https://webeep.polimi.it/mod/folder/view.php?id=10">Course lectures</a><a href="https://webeep.polimi.it/mod/page/view.php?id=11">Links</a></main>'
                elif '/mod/folder/view.php' in url:
                    body = '<div id="region-main"><a href="https://webeep.polimi.it/pluginfile.php/1/mod_folder/content/0/week1/intro.pdf">intro.pdf</a></div>'
                else:
                    body = '<div id="region-main"><p>Useful links</p><a href="https://example.com">Reference</a><script>window.fixture=true</script><form><input type="password"></form></div>'
                await route.fulfill(content_type='text/html', body=body)
            await context.route('**/*', respond)
            try:
                assets = await discover_materials(context, {'url': 'https://webeep.polimi.it/course/view.php?id=1', 'label': 'Parallel Computing'})
                self.assertEqual(len(assets), 2)
                file = next(a for a in assets if a['kind'] == 'file')
                self.assertEqual(file['relative'], 'week1/intro.pdf')
                page = next(a for a in assets if a['kind'] == 'page')
                self.assertIn('https://example.com', page['body'])
                self.assertNotIn('<script', page['body'])
                self.assertNotIn('<form', page['body'])
            finally:
                await browser.close()
