import os
import tempfile
import unittest
from pathlib import Path

from playwright.async_api import async_playwright

from polimi_lectures.browser import auto_controls, resolve, scan
from polimi_lectures.core import Catalog
from polimi_lectures.session import BrowserAssistant, fill_webex_email, start_webex_playback


RID = "abcdef0123456789abcdef0123456789"
URL = "https://politecnicomilano.webex.com/recordingservice/sites/politecnicomilano/recording/playback/" + RID


class BrowserTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.catalog = Catalog(self.directory.name)
        self.playwright = await async_playwright().start()
        if not Path(self.playwright.chromium.executable_path).exists():
            await self.playwright.stop()
            self.catalog.db.close()
            self.directory.cleanup()
            self.skipTest("Chromium non installato")
        self.browser = await self.playwright.chromium.launch(headless=True)
        self.context = await self.browser.new_context()

    async def asyncTearDown(self):
        await self.context.close()
        await self.browser.close()
        await self.playwright.stop()
        self.catalog.db.close()
        self.directory.cleanup()

    async def test_scan_collects_row_date_and_deduplicates(self):
        page = await self.context.new_page()
        await page.set_content('<table><tr><td>14/10/2026</td><td>Lezione MPI</td><td><a href="%s">Play</a></td></tr></table>' % URL)
        self.assertEqual(await scan(self.context, self.catalog, "Parallel Computing"), 1)
        self.assertEqual(await scan(self.context, self.catalog, "Parallel Computing"), 0)
        self.assertEqual(self.catalog.rows()[0]["date"], "2026-10-14")

    async def test_playback_popup_is_collected_and_closed(self):
        async def fake_webex(route):
            await route.fulfill(body="<html><title>Webex recording</title></html>", content_type="text/html")
        await self.context.route("https://politecnicomilano.webex.com/**", fake_webex)
        page = await self.context.new_page()
        await page.set_content('<table><tr><td>14/10/2026</td><td><button onclick="window.open(\'%s\')">Riproduci</button></td></tr></table>' % URL)
        await auto_controls(self.context, page, self.catalog, "Parallel Computing")
        self.assertEqual(len(self.catalog.rows()), 1)
        self.assertEqual(self.catalog.rows()[0]["date"], "2026-10-14")
        self.assertEqual(len(self.context.pages), 1)

    async def test_stream_response_resolves_direct_mp4_without_real_webex(self):
        async def fake_webex(route):
            if "/stream" in route.request.url:
                await route.fulfill(json={"recordName": "MPI", "fallbackPlaySrc": "https://cdn.webex.com/video.mp4?token=private"})
            else:
                await route.fulfill(content_type="text/html", body='<script>fetch("/webappng/api/v1/recordings/%s/stream")</script>' % RID)
        await self.context.route("https://politecnicomilano.webex.com/**", fake_webex)
        self.catalog.add("Parallel Computing", URL)
        candidates, cookies, agent, referer, title = await resolve(self.context, self.catalog.rows()[0], timeout=3)
        self.assertEqual(candidates[0][0], "mp4")
        self.assertEqual(title, "MPI")
        self.assertNotIn("token=private", (Path(self.directory.name) / ".state" / "catalog.sqlite3").read_bytes().decode("latin1"))

    async def test_webex_email_is_submitted_once(self):
        async def login(route):
            await route.fulfill(content_type="text/html", body='''<label for="email">Indirizzo e-mail</label>
                <input id="email" type="email"><button onclick="document.body.dataset.submitted='yes'">Accedi</button>''')
        await self.context.route("https://idbroker.webex.com/**", login)
        page = await self.context.new_page()
        await page.goto("https://idbroker.webex.com/login")
        email = "student@example.edu"
        self.assertTrue(await fill_webex_email(page, email))
        self.assertEqual(await page.locator("#email").input_value(), email)
        self.assertEqual(await page.locator("body").get_attribute("data-submitted"), "yes")
        self.assertFalse(await fill_webex_email(page, email))

    async def test_password_step_and_other_domains_are_left_to_user(self):
        async def login(route):
            await route.fulfill(content_type="text/html", body='''<input type="email"><input type="password">
                <button>Accedi</button>''')
        await self.context.route("https://idbroker.webex.com/**", login)
        await self.context.route("https://other.example/**", login)
        page = await self.context.new_page()
        for url in ("https://idbroker.webex.com/login", "https://other.example/login"):
            await page.goto(url)
            self.assertFalse(await fill_webex_email(page, "student@example.edu"))
            self.assertEqual(await page.locator('input[type="email"]').input_value(), "")

    async def test_debug_html_is_private_redacted_and_deduplicated(self):
        async def document(route):
            await route.fulfill(content_type="text/html", body='''<h1>Webex test</h1>
                <input type="password" value="PASSWORD_SECRET">
                <input type="hidden" value="FORM_TOKEN_SECRET">''')
        await self.context.route("https://idbroker.webex.com/**", document)
        page = await self.context.new_page()
        await page.goto("https://idbroker.webex.com/login?token=URL_TOKEN")
        assistant = BrowserAssistant(self.context, Path(self.directory.name), debug_html=True)
        await assistant.save_page(page)
        await assistant.save_page(page)
        files = list(assistant.directory.glob("*.html"))
        self.assertEqual(len(files), 1)
        content = files[0].read_text()
        self.assertIn("Webex test", content)
        self.assertNotIn("PASSWORD_SECRET", content)
        self.assertNotIn("FORM_TOKEN_SECRET", content)
        self.assertEqual(files[0].stat().st_mode & 0o777, 0o600)
        self.assertNotIn("URL_TOKEN", next(assistant.directory.glob("*.json")).read_text())
        self.assertEqual(await page.locator('input[type="password"]').input_value(), "PASSWORD_SECRET")

    async def test_background_assistant_handles_new_login_page_and_saves_html(self):
        async def login(route):
            await route.fulfill(content_type="text/html", body='''<input type="email">
                <button onclick="document.body.dataset.submitted='yes'">Accedi</button>''')
        await self.context.route("https://idbroker.webex.com/**", login)
        assistant = BrowserAssistant(self.context, Path(self.directory.name), "student@example.edu", True)
        assistant.start()
        try:
            page = await self.context.new_page()
            await page.goto("https://idbroker.webex.com/login")
            await page.wait_for_function("document.body.dataset.submitted === 'yes'", timeout=7000)
        finally:
            await assistant.stop()
        self.assertGreater(len(list(assistant.directory.glob('*.html'))), 0)
        self.assertEqual(len(assistant.tasks), 0)

    async def test_actual_webex_role_link_and_disabled_button_are_supported(self):
        async def login(route):
            await route.fulfill(content_type='text/html', body='''<label>Indirizzo e-mail</label>
                <input id="IDToken1" name="IDToken1" type="email" oninput="document.querySelector('#IDButton2').disabled=!this.value.includes('@')">
                <button id="IDButton2" name="btnOK" type="submit" role="link" disabled onclick="document.body.dataset.submitted='yes'">Accedi</button>''')
        await self.context.route('https://idbroker-eu.webex.com/**', login)
        page = await self.context.new_page()
        await page.goto('https://idbroker-eu.webex.com/idb/saml2/jsp/doSSO.jsp')
        self.assertTrue(await fill_webex_email(page, 'student@example.edu'))
        self.assertEqual(await page.locator('#IDToken1').input_value(), 'student@example.edu')
        self.assertEqual(await page.locator('body').get_attribute('data-submitted'), 'yes')

    async def test_disabled_email_retries_do_not_steal_input_focus(self):
        async def login(route):
            await route.fulfill(content_type='text/html', body='''<input id="other"><input id="IDToken1" type="email">
                <button id="IDButton2" role="link" disabled>Accedi</button>''')
        await self.context.route('https://idbroker-eu.webex.com/**', login)
        page = await self.context.new_page()
        await page.goto('https://idbroker-eu.webex.com/login')
        await page.evaluate("document.querySelector('#other').focus()")
        for _ in range(2):
            self.assertFalse(await fill_webex_email(page, 'student@example.edu'))
            self.assertEqual(await page.evaluate('document.activeElement.id'), 'other')

    async def test_player_is_started_once_without_manual_play(self):
        async def player(route):
            await route.fulfill(content_type='text/html', body='''<video></video><script>
                const video=document.querySelector('video'); window.playCount=0;
                video.play=async () => {window.playCount++};
            </script>''')
        await self.context.route('https://politecnicomilano.webex.com/**', player)
        page = await self.context.new_page()
        await page.goto(URL)
        self.assertTrue(await start_webex_playback(page))
        self.assertFalse(await start_webex_playback(page))
        self.assertEqual(await page.evaluate('window.playCount'), 1)
