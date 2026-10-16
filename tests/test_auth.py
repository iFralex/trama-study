import json
import tempfile
import unittest
from unittest.mock import AsyncMock, patch
from pathlib import Path

from playwright.async_api import async_playwright

from polimi_lectures.auth import restore_auth, save_auth
from polimi_lectures.guided import login_and_courses
from polimi_lectures.session import BrowserAssistant


class AuthTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.path = Path(self.temp.name) / '.state/auth-state.json'
        self.pw = await async_playwright().start()
        if not Path(self.pw.chromium.executable_path).exists():
            await self.pw.stop()
            self.temp.cleanup()
            self.skipTest('Chromium non installato')
        self.browser = await self.pw.chromium.launch(headless=True)

    async def asyncTearDown(self):
        await self.browser.close()
        await self.pw.stop()
        self.temp.cleanup()

    async def test_session_cookie_survives_context_restart_and_skips_login(self):
        first = await self.browser.new_context()
        await first.add_cookies([{'name': 'MoodleSession', 'value': 'fixture-session',
                                 'domain': 'webeep.polimi.it', 'path': '/', 'secure': True}])
        await save_auth(first, self.path)
        await first.close()
        second = await self.browser.new_context()
        self.assertTrue(await restore_auth(second, self.path))
        async def page(route):
            if 'MoodleSession=fixture-session' in route.request.headers.get('cookie', ''):
                await route.fulfill(content_type='text/html', body='<a href="https://webeep.polimi.it/course/view.php?id=1">Parallel Computing</a>')
            else:
                await route.fulfill(content_type='text/html', body='<input type="password">')
        await second.route('**/*', page)
        _, courses = await login_and_courses(second, timeout=2)
        self.assertEqual(len(courses), 1)
        self.assertEqual(self.path.stat().st_mode & 0o777, 0o600)
        await second.close()

    async def test_only_polimi_webex_state_is_saved_and_local_storage_is_restored(self):
        first = await self.browser.new_context()
        await first.add_cookies([
            {'name': 'webex', 'value': 'fixture', 'domain': '.webex.com', 'path': '/'},
            {'name': 'posteid', 'value': 'not-exported', 'domain': 'posteid.poste.it', 'path': '/'},
        ])
        await first.route('**/*', lambda route: route.fulfill(content_type='text/html', body='<title>fixture</title>'))
        page = await first.new_page()
        await page.goto('https://webeep.polimi.it/')
        await page.evaluate("localStorage.setItem('fixture-key','fixture-value')")
        await save_auth(first, self.path)
        data = json.loads(self.path.read_text())
        self.assertEqual([c['name'] for c in data['cookies']], ['webex'])
        await first.close()
        second = await self.browser.new_context()
        await restore_auth(second, self.path)
        await second.route('**/*', lambda route: route.fulfill(content_type='text/html', body='<title>fixture</title>'))
        page = await second.new_page()
        await page.goto('https://webeep.polimi.it/')
        self.assertEqual(await page.evaluate("localStorage.getItem('fixture-key')"), 'fixture-value')
        await second.close()

    async def test_expired_cookie_is_not_restored_or_extended(self):
        self.path.parent.mkdir()
        self.path.write_text(json.dumps({'cookies': [{'name': 'expired', 'value': 'fixture', 'domain': 'webeep.polimi.it',
                                                      'path': '/', 'expires': 1}], 'origins': []}))
        context = await self.browser.new_context()
        self.assertFalse(await restore_auth(context, self.path))
        self.assertEqual(await context.cookies(), [])
        await context.close()

    async def test_newer_profile_cookie_is_not_overwritten_by_saved_state(self):
        context = await self.browser.new_context()
        old = {'name': 'MoodleSession', 'value': 'old', 'domain': 'webeep.polimi.it', 'path': '/'}
        await context.add_cookies([old])
        await save_auth(context, self.path)
        await context.add_cookies([dict(old, value='new')])
        await restore_auth(context, self.path)
        self.assertEqual((await context.cookies())[0]['value'], 'new')
        await context.close()

    async def test_assistant_saves_auth_before_context_is_closed(self):
        context = await self.browser.new_context()
        await context.add_cookies([{'name': 'MoodleSession', 'value': 'fixture', 'domain': 'webeep.polimi.it', 'path': '/'}])
        assistant = BrowserAssistant(context, Path(self.temp.name), auth_path=self.path)
        assistant.start()
        await assistant.stop()
        self.assertTrue(self.path.exists())
        self.assertEqual(json.loads(self.path.read_text())['cookies'][0]['name'], 'MoodleSession')
        await context.close()

    async def test_checkpoint_does_not_create_tabs_or_call_storage_state(self):
        context = await self.browser.new_context()
        await context.route('**/*', lambda route: route.fulfill(content_type='text/html', body='<title>fixture</title>'))
        page = await context.new_page()
        await page.goto('https://webeep.polimi.it/')
        await page.evaluate("localStorage.setItem('saved-origin','fixture')")
        await save_auth(context, self.path)
        await page.close()
        remaining = await context.new_page()
        await remaining.goto('https://politecnicomilano.webex.com/')
        opened = []
        context.on('page', lambda page: opened.append(page))
        with patch.object(context, 'storage_state', new=AsyncMock(side_effect=AssertionError('Non deve aprire schede temporanee'))):
            await save_auth(context, self.path)
            await save_auth(context, self.path)
        self.assertEqual(opened, [])
        self.assertEqual(context.pages, [remaining])
        origins = json.loads(self.path.read_text())['origins']
        self.assertTrue(any(o['origin'] == 'https://webeep.polimi.it' for o in origins))
        await context.close()
